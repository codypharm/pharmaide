"""Analysis graph clinical summary node behavior."""

import json
from datetime import timedelta
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
    MedicationGrounding,
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
