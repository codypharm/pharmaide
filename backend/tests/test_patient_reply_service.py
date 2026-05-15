"""Database-backed patient-reply draft context assembly."""

from datetime import date
from uuid import uuid4

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply import PatientReplyDraft
from app.db.models import ConversationMessage, Medication, Patient, Treatment, TreatmentAnalysis
from app.services.patient_reply_drafts import TreatmentNotFound, draft_patient_reply_for_treatment


async def test_draft_patient_reply_for_treatment_builds_context_from_database(
    db_session: AsyncSession,
) -> None:
    seen: dict[str, str] = {}
    treatment = await _persist_reply_context(db_session)

    def model_function(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen["prompt"] = _user_prompt(messages)
        output_tool = info.output_tools[0]
        return ModelResponse(
            parts=[
                ToolCallPart(
                    output_tool.name,
                    {
                        "message": "I will ask the pharmacist to review your nausea.",
                        "requires_pharmacist_review": True,
                        "escalation_reason": "side_effect",
                        "confidence": 0.78,
                    },
                )
            ],
            model_name="patient-reply-service-test",
        )

    agent: Agent[None, PatientReplyDraft] = Agent(
        FunctionModel(model_function),
        output_type=PatientReplyDraft,
    )

    draft = await draft_patient_reply_for_treatment(
        db_session,
        treatment.id,
        patient_message="I feel nauseous after the morning dose.",
        agent=agent,
    )

    assert draft.escalation_reason == "side_effect"
    assert "Amoxicillin" in seen["prompt"]
    assert "500 mg" in seen["prompt"]
    assert "Monitor recovery and stomach tolerance" in seen["prompt"]
    assert "I took my first dose this morning" in seen["prompt"]
    assert "Clinical summary: monitor gastrointestinal symptoms." in seen["prompt"]


async def test_draft_patient_reply_for_treatment_raises_for_unknown_treatment(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(TreatmentNotFound):
        await draft_patient_reply_for_treatment(
            db_session,
            uuid4(),
            patient_message="Hello",
            agent=Agent(FunctionModel(lambda *_: ModelResponse(parts=[]))),
        )


async def _persist_reply_context(session: AsyncSession) -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn="REPLY-SVC-001",
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        clinical_objective="Monitor recovery and stomach tolerance",
    )
    session.add(treatment)
    await session.flush()
    session.add(
        Medication(
            treatment_id=treatment.id,
            name="Amoxicillin",
            dosage="500 mg",
            frequency="Three Times Daily (TID)",
            duration="7 days",
            objective="Treat infection",
            ordinal=0,
        )
    )
    session.add(
        ConversationMessage(
            treatment_id=treatment.id,
            direction="inbound",
            sender_type="patient",
            channel="whatsapp",
            status="received",
            body="I took my first dose this morning.",
        )
    )
    session.add(
        TreatmentAnalysis(
            treatment_id=treatment.id,
            status="completed",
            result={
                "reasoning": {
                    "summary": "Clinical summary: monitor gastrointestinal symptoms."
                }
            },
        )
    )
    await session.flush()
    return treatment


def _user_prompt(messages: list[ModelMessage]) -> str:
    for message in messages:
        if isinstance(message, ModelRequest):
            for part in message.parts:
                if isinstance(part, UserPromptPart) and isinstance(part.content, str):
                    return part.content
    raise AssertionError("expected a user prompt")
