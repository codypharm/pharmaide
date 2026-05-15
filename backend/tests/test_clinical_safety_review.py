"""Clinical safety review node behavior."""

from uuid import UUID

import pytest
import structlog
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalSafetyReview,
    KBCitation,
    MedicationGrounding,
)
from app.agents.nodes.clinical_safety_review import (
    build_clinical_safety_agent,
    review_clinical_safety,
)

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
                "objective": "anticoagulation",
            },
        ],
        "groundings": [
            MedicationGrounding(
                medication_id=FIRST_MEDICATION_ID,
                medication_name="Lisinopril",
                rxcui="29046",
                normalized_name="lisinopril",
                confidence=0.95,
            )
        ],
        "ddi_warnings": [],
        "kb_citations": [
            KBCitation(
                chunk_id=UUID("44444444-4444-4444-4444-444444444444"),
                document_id=UUID("55555555-5555-5555-5555-555555555555"),
                document_title="Lisinopril Label",
                source_type="dailymed",
                source_uri="dailymed://setid-1",
                text="Monitor for symptomatic hypotension.",
                score=0.9,
            )
        ],
        "degraded": True,
    }


def test_build_clinical_safety_agent_defaults_to_high_accuracy_model() -> None:
    agent = build_clinical_safety_agent()

    assert agent.model == "openai:gpt-5"


async def test_review_clinical_safety_writes_validated_model_review() -> None:
    agent = build_clinical_safety_agent(
        model=TestModel(
            custom_output_args={
                "source_type": "model_review",
                "possible_interactions": ["Review blood pressure effects with current regimen."],
                "monitoring_concerns": ["Monitor dizziness or hypotension."],
                "counseling_points": ["Advise patient to report fainting."],
                "missing_information": ["Recent blood pressure readings unavailable."],
                "confidence": 0.67,
                "requires_pharmacist_review": True,
            }
        )
    )

    reviewed = await review_clinical_safety(_state(), agent=agent)

    assert reviewed["clinical_safety_review"] == ClinicalSafetyReview(
        possible_interactions=["Review blood pressure effects with current regimen."],
        monitoring_concerns=["Monitor dizziness or hypotension."],
        counseling_points=["Advise patient to report fainting."],
        missing_information=["Recent blood pressure readings unavailable."],
        confidence=0.67,
        requires_pharmacist_review=True,
    )
    assert reviewed["ddi_warnings"] == []


async def test_review_clinical_safety_prompt_forbids_database_claims() -> None:
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
                        "source_type": "model_review",
                        "possible_interactions": [],
                        "monitoring_concerns": ["Monitor for symptomatic hypotension."],
                        "counseling_points": [],
                        "missing_information": [],
                        "confidence": 0.7,
                        "requires_pharmacist_review": True,
                    },
                )
            ],
            model_name="safety-review-test",
        )

    agent: Agent[None, ClinicalSafetyReview] = build_clinical_safety_agent(
        model=FunctionModel(model_function)
    )

    await review_clinical_safety(_state(), agent=agent)

    assert "do not present findings as database-confirmed" in seen["instructions"].lower()
    assert "source_type fixed to model_review" in seen["instructions"].lower()
    assert "requires_pharmacist_review fixed to true" in seen["instructions"].lower()
    assert "not a licensed ddi database result" in seen["prompt"].lower()
    assert "Lisinopril" in seen["prompt"]
    assert "Monitor for symptomatic hypotension." in seen["prompt"]


async def test_review_clinical_safety_skips_when_agent_not_configured() -> None:
    reviewed = await review_clinical_safety(_state(), agent=None)

    assert reviewed["clinical_safety_review"] is None


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if not isinstance(message, ModelResponse):
            for part in message.parts:
                if isinstance(part, UserPromptPart):
                    return str(part.content)
    raise AssertionError("user prompt not found")
