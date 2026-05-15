"""Typed patient-reply draft agent behavior."""

from uuid import UUID

import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from app.agents.patient_reply import (
    ConversationMessageContext,
    MedicationContext,
    PatientReplyContext,
    PatientReplyDraft,
    build_patient_reply_agent,
    draft_patient_reply,
)


def test_build_patient_reply_agent_defaults_to_high_accuracy_model() -> None:
    agent = build_patient_reply_agent()

    assert agent.model == "openai:gpt-5"


def test_patient_reply_draft_requires_reason_when_held_for_review() -> None:
    with pytest.raises(ValidationError):
        PatientReplyDraft(
            message="I will ask the pharmacist to review this.",
            requires_pharmacist_review=True,
            escalation_reason="none",
            confidence=0.8,
        )


async def test_draft_patient_reply_returns_validated_output_and_prompt_context() -> None:
    seen: dict[str, str] = {}

    def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["instructions"] = info.instructions or ""
        seen["prompt"] = _user_prompt(messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "message": (
                            "Thanks for telling us. I will ask the pharmacist to review "
                            "your nausea before advising further."
                        ),
                        "requires_pharmacist_review": True,
                        "escalation_reason": "side_effect",
                        "confidence": 0.82,
                    },
                )
            ],
            model_name="patient-reply-test",
        )

    agent: Agent[None, PatientReplyDraft] = build_patient_reply_agent(
        model=FunctionModel(model_function)
    )

    draft = await draft_patient_reply(
        PatientReplyContext(
            treatment_id=UUID("11111111-1111-4111-8111-111111111111"),
            clinical_objective="Monitor recovery and gastrointestinal tolerance.",
            patient_message="I feel nauseous after the morning dose.",
            medications=[
                MedicationContext(
                    name="Metronidazole",
                    dosage="400 mg",
                    frequency="Three Times Daily (TID)",
                    duration="7 days",
                    objective="Treat infection",
                )
            ],
            recent_messages=[
                ConversationMessageContext(
                    direction="inbound",
                    sender_type="patient",
                    status="received",
                    body="I took the first dose this morning.",
                )
            ],
            latest_analysis_summary="Monitor for gastrointestinal adverse effects.",
        ),
        agent=agent,
    )

    assert draft.requires_pharmacist_review is True
    assert draft.escalation_reason == "side_effect"
    assert "pharmacist" in draft.message.lower()
    assert "validated patient-reply draft" in seen["instructions"].lower()
    assert "do not change medication doses" in seen["instructions"].lower()
    assert "Metronidazole" in seen["prompt"]
    assert "Monitor for gastrointestinal adverse effects" in seen["prompt"]
    assert "I feel nauseous after the morning dose" in seen["prompt"]


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    raise AssertionError("expected a user prompt")
