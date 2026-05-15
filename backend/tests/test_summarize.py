"""Analysis graph clinical summary node behavior."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
    ClinicalSafetyReview,
    KBCitation,
    MedicationGrounding,
    PatientCheckInState,
    ReminderSlot,
    Schedule,
)
from app.agents.nodes.summarize import (
    build_summary_agent,
    build_summary_with_schedule_agent,
    summarize_treatment,
)
from app.logging_setup import configure_logging

FIRST_MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_MEDICATION_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _state() -> AnalysisState:
    return {
        "medications": [
            {
                "id": FIRST_MEDICATION_ID,
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "BID",
                "duration": "1 day",
                "objective": "blood pressure control",
            },
            {
                "id": SECOND_MEDICATION_ID,
                "name": "Warfarin",
                "dosage": "5 mg",
                "frequency": "Q8H",
                "duration": "1 day",
                "objective": None,
            },
        ],
        "groundings": [
            MedicationGrounding(
                medication_id=FIRST_MEDICATION_ID,
                medication_name="Lisinopril",
                rxcui="29046",
                normalized_name="lisinopril",
                confidence=0.95,
            ),
            MedicationGrounding(
                medication_id=SECOND_MEDICATION_ID,
                medication_name="Warfarin",
                rxcui=None,
                normalized_name=None,
                confidence=0,
            ),
        ],
        "ddi_warnings": [],
        "schedule": Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=FIRST_MEDICATION_ID,
                    offset_from_start=timedelta(hours=0),
                    human_label="twice daily dose 1",
                )
            ]
        ),
        "degraded": True,
        "needs_llm_parse": False,
    }


def _records_with_event(captured: str, event: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in captured.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == event:
            records.append(record)
    return records


def test_build_summary_agent_defaults_to_accuracy_then_latency_model() -> None:
    agent = build_summary_agent()

    assert agent.model == "openai:gpt-5-mini"


def test_build_summary_with_schedule_agent_defaults_to_accuracy_then_latency_model() -> None:
    agent = build_summary_with_schedule_agent()

    assert agent.model == "openai:gpt-5-mini"


async def test_summarize_treatment_writes_validated_clinical_reasoning() -> None:
    agent = build_summary_agent(
        model=TestModel(
            custom_output_args={
                "summary": "Grounding is incomplete and pharmacist review is needed.",
                "red_flags": ["One medication was not grounded."],
                "confidence": 0.72,
            }
        )
    )

    summarized = await summarize_treatment(_state(), agent=agent)

    assert summarized["reasoning"] == ClinicalReasoning(
        summary="Grounding is incomplete and pharmacist review is needed.",
        red_flags=["One medication was not grounded."],
        confidence=0.72,
    )


async def test_summarize_treatment_merges_validated_llm_schedule_when_needed() -> None:
    state = _state()
    state["needs_llm_parse"] = True
    agent = build_summary_with_schedule_agent(
        model=TestModel(
            custom_output_args={
                "reasoning": {
                    "summary": "One schedule instruction required LLM parsing.",
                    "red_flags": [],
                    "confidence": 0.68,
                },
                "schedule": {
                    "reminders": [
                        {
                            "medication_id": str(SECOND_MEDICATION_ID),
                            "offset_from_start": "PT10H",
                            "human_label": "LLM proposed evening dose",
                        }
                    ]
                },
            }
        )
    )

    summarized = await summarize_treatment(state, schedule_agent=agent)

    assert summarized["reasoning"] == ClinicalReasoning(
        summary="One schedule instruction required LLM parsing.",
        red_flags=[],
        confidence=0.68,
    )
    assert summarized["schedule"] is not None
    assert [
        (slot.medication_id, slot.offset_from_start, slot.human_label)
        for slot in summarized["schedule"].reminders
    ] == [
        (FIRST_MEDICATION_ID, timedelta(hours=0), "twice daily dose 1"),
        (SECOND_MEDICATION_ID, timedelta(hours=10), "LLM proposed evening dose"),
    ]


async def test_summarize_treatment_accepts_no_llm_schedule_proposal() -> None:
    state = _state()
    state["needs_llm_parse"] = True
    agent = build_summary_with_schedule_agent(
        model=TestModel(
            custom_output_args={
                "reasoning": {
                    "summary": "Schedule remains unavailable for ambiguous instructions.",
                    "red_flags": ["Pharmacist should review the ambiguous schedule."],
                    "confidence": 0.55,
                },
                "schedule": None,
            }
        )
    )

    summarized = await summarize_treatment(state, schedule_agent=agent)

    assert summarized["reasoning"] == ClinicalReasoning(
        summary="Schedule remains unavailable for ambiguous instructions.",
        red_flags=["Pharmacist should review the ambiguous schedule."],
        confidence=0.55,
    )
    assert summarized["schedule"] == state["schedule"]


async def test_summarize_treatment_prompt_restricts_model_to_state_content() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "summary": "State-only summary.",
                        "red_flags": [],
                        "confidence": 0.8,
                    },
                )
            ],
            model_name="summary-test",
        )

    agent: Agent[None, ClinicalReasoning] = build_summary_agent(model=FunctionModel(model_function))

    await summarize_treatment(_state(), agent=agent)

    assert "never invent medications" in seen["instructions"].lower()
    assert "validated AnalysisState" in seen["prompt"]
    assert "Lisinopril" in seen["prompt"]
    assert "Warfarin" in seen["prompt"]
    assert "degraded: True" in seen["prompt"]


async def test_summarize_treatment_prompt_includes_kb_citations() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "summary": "KB citations were considered.",
                        "red_flags": [],
                        "confidence": 0.82,
                    },
                )
            ],
            model_name="summary-kb-test",
        )

    state = _state()
    state["kb_citations"] = [
        KBCitation(
            chunk_id=UUID("44444444-4444-4444-4444-444444444444"),
            document_id=UUID("55555555-5555-5555-5555-555555555555"),
            document_title="Anticoagulation Protocol",
            source_uri="local://kb/anticoagulation.pdf",
            text="Warfarin requires INR monitoring.",
            score=0.92,
        )
    ]
    agent: Agent[None, ClinicalReasoning] = build_summary_agent(model=FunctionModel(model_function))

    await summarize_treatment(state, agent=agent)

    assert "kb_citations:" in seen["prompt"]
    assert "Anticoagulation Protocol" in seen["prompt"]
    assert "source_type=user_upload" in seen["prompt"]
    assert "Warfarin requires INR monitoring." in seen["prompt"]


async def test_summarize_treatment_prompt_includes_clinical_safety_review() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "summary": "Safety review was considered.",
                        "red_flags": [],
                        "confidence": 0.82,
                    },
                )
            ],
            model_name="summary-safety-review-test",
        )

    state = _state()
    state["clinical_safety_review"] = ClinicalSafetyReview(
        possible_interactions=["AI review suggests monitoring overlap."],
        monitoring_concerns=["Monitor dizziness."],
        counseling_points=["Report fainting."],
        missing_information=["Recent BP unavailable."],
        confidence=0.68,
        requires_pharmacist_review=True,
    )
    agent: Agent[None, ClinicalReasoning] = build_summary_agent(model=FunctionModel(model_function))

    await summarize_treatment(state, agent=agent)

    assert "clinical_safety_review:" in seen["prompt"]
    assert "source_type=model_review" in seen["prompt"]
    assert "requires_pharmacist_review=True" in seen["prompt"]
    assert "AI review suggests monitoring overlap." in seen["prompt"]


async def test_summarize_treatment_preserves_safety_review_concerns_as_red_flags() -> None:
    state = _state()
    state["clinical_safety_review"] = ClinicalSafetyReview(
        possible_interactions=["Review possible bleeding-risk overlap."],
        monitoring_concerns=["Monitor for bruising."],
        counseling_points=["Report unusual bleeding."],
        missing_information=["Recent INR unavailable."],
        confidence=0.42,
        requires_pharmacist_review=True,
    )
    agent = build_summary_agent(
        model=TestModel(
            custom_output_args={
                "summary": "The treatment was reviewed.",
                "red_flags": [],
                "confidence": 0.9,
            }
        )
    )

    summarized = await summarize_treatment(state, agent=agent)

    assert summarized["reasoning"] == ClinicalReasoning(
        summary="The treatment was reviewed.",
        red_flags=[
            "Clinical safety review found possible interaction concerns.",
            "Clinical safety review found monitoring concerns.",
            "Clinical safety review found missing information for pharmacist review.",
        ],
        confidence=0.42,
    )


async def test_summarize_treatment_guards_llm_schedule_reasoning_with_safety_review() -> None:
    state = _state()
    state["needs_llm_parse"] = True
    state["clinical_safety_review"] = ClinicalSafetyReview(
        possible_interactions=[],
        monitoring_concerns=["Monitor for dizziness."],
        counseling_points=[],
        missing_information=[],
        confidence=0.61,
        requires_pharmacist_review=True,
    )
    agent = build_summary_with_schedule_agent(
        model=TestModel(
            custom_output_args={
                "reasoning": {
                    "summary": "Schedule proposal generated.",
                    "red_flags": [],
                    "confidence": 0.88,
                },
                "schedule": None,
            }
        )
    )

    summarized = await summarize_treatment(state, schedule_agent=agent)

    assert summarized["reasoning"] == ClinicalReasoning(
        summary="Schedule proposal generated.",
        red_flags=["Clinical safety review found monitoring concerns."],
        confidence=0.61,
    )


async def test_summarize_treatment_prompt_includes_patient_reported_updates() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "summary": "Patient update was considered.",
                        "red_flags": ["Patient reports no improvement."],
                        "confidence": 0.79,
                    },
                )
            ],
            model_name="summary-check-ins-test",
        )

    state = _state()
    state["patient_check_ins"] = [
        PatientCheckInState(
            id=UUID("66666666-6666-6666-6666-666666666666"),
            report_type="not_improving",
            source="patient",
            message="Patient says symptoms are not improving after three days.",
            observed_at=datetime(2026, 5, 18, 9, 15, tzinfo=UTC),
            created_at=datetime(2026, 5, 18, 10, 0, tzinfo=UTC),
        )
    ]
    agent: Agent[None, ClinicalReasoning] = build_summary_agent(model=FunctionModel(model_function))

    await summarize_treatment(state, agent=agent)

    assert "patient_check_ins:" in seen["prompt"]
    assert "report_type=not_improving" in seen["prompt"]
    assert "source=patient" in seen["prompt"]
    assert "Patient says symptoms are not improving after three days." in seen["prompt"]


async def test_summarize_treatment_prompt_requests_schedule_only_when_needed() -> None:
    seen: dict[str, str] = {}

    def model_function(_messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(_messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "reasoning": {
                            "summary": "Schedule proposal generated from state only.",
                            "red_flags": [],
                            "confidence": 0.75,
                        },
                        "schedule": None,
                    },
                )
            ],
            model_name="summary-schedule-test",
        )

    state = _state()
    state["needs_llm_parse"] = True
    agent: Agent[None, ClinicalReasoningWithSchedule] = build_summary_with_schedule_agent(
        model=FunctionModel(model_function)
    )

    await summarize_treatment(state, schedule_agent=agent)

    assert "propose schedule.reminders only for medications whose frequency or duration" in (
        seen["instructions"].lower()
    )
    assert "do not invent frequency, duration, dose timing" in seen["instructions"].lower()
    assert "do not create reminders for prn/as-needed medications" in seen["instructions"].lower()
    assert "do not duplicate them" in seen["instructions"].lower()
    assert "pharmacist-review drafts" in seen["instructions"].lower()
    assert "needs_llm_parse: True" in seen["prompt"]


async def test_summarize_treatment_logs_non_phi_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    agent = build_summary_agent(
        model=TestModel(
            custom_output_args={
                "summary": "Analysis requires pharmacist review.",
                "red_flags": [],
                "confidence": 0.9,
            }
        )
    )

    await summarize_treatment(_state(), agent=agent)

    records = _records_with_event(capsys.readouterr().out, "clinical_reasoning_generated")

    assert records
    assert records[-1]["medication_count"] == 2
    assert records[-1]["red_flag_count"] == 0
    assert records[-1]["confidence"] == 0.9
    assert "Analysis requires pharmacist review." not in json.dumps(records[-1])
    assert "Lisinopril" not in json.dumps(records[-1])


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    raise AssertionError("expected a user prompt")
