"""Internal worker seam for buffered patient messages."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply import PatientReplyDraft
from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.db.models import ConversationMessage
from app.services import task_runner
from app.services.patient_message_buffer import buffer_patient_message


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Buffered-message tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_process_buffered_patient_turn_creates_one_assistant_reply_without_duplicate_inbound(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "BUFFER-ENDPOINT-001")
    await buffer_patient_message(db_session, treatment_id=treatment_id, message="I took it")
    await buffer_patient_message(db_session, treatment_id=treatment_id, message="but I vomited")
    await _age_buffered_messages(db_session, treatment_id)
    _patch_generated_reply(monkeypatch)
    _patch_safety_decision(monkeypatch, treatment_id)

    response = await app_client.post(
        f"/internal/treatments/{treatment_id}/process-buffered-patient-turn"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["processed_count"] == 2
    assert payload["assistant_message_id"] is not None
    assert payload["assistant_status"] == "held_for_review"

    messages = (
        await db_session.execute(
            select(ConversationMessage).order_by(
                ConversationMessage.created_at.asc(),
                ConversationMessage.id.asc(),
            )
        )
    ).scalars().all()
    assert [(message.direction, message.sender_type, message.status) for message in messages] == [
        ("inbound", "patient", "received"),
        ("inbound", "patient", "received"),
        ("outbound", "assistant", "held_for_review"),
    ]
    assert all(message.processed_at is not None for message in messages[:2])
    assert "I took it\nbut I vomited" not in [message.body for message in messages]


@pytest.mark.usefixtures("postgres_container")
async def test_process_buffered_patient_turn_returns_zero_when_no_messages(
    app_client: AsyncClient,
) -> None:
    treatment_id = await _create_treatment(app_client, "BUFFER-ENDPOINT-002")

    response = await app_client.post(
        f"/internal/treatments/{treatment_id}/process-buffered-patient-turn"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "processed_count": 0,
        "assistant_message_id": None,
        "assistant_status": None,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_process_buffered_patient_turn_waits_for_default_debounce_window(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "BUFFER-ENDPOINT-004")
    await buffer_patient_message(db_session, treatment_id=treatment_id, message="hello")

    response = await app_client.post(
        f"/internal/treatments/{treatment_id}/process-buffered-patient-turn"
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "processed_count": 0,
        "assistant_message_id": None,
        "assistant_status": None,
    }
    message = await db_session.scalar(select(ConversationMessage))
    assert message is not None
    assert message.processed_at is None


@pytest.mark.usefixtures("postgres_container")
async def test_process_buffered_patient_turn_keeps_messages_retryable_when_reply_fails(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment_id = await _create_treatment(app_client, "BUFFER-ENDPOINT-003")
    await buffer_patient_message(db_session, treatment_id=treatment_id, message="I feel worse")
    await _age_buffered_messages(db_session, treatment_id)

    async def fail_draft_patient_reply_for_treatment(*args: object, **kwargs: object) -> object:
        raise RuntimeError("draft failed")

    monkeypatch.setattr(
        "app.api.internal.draft_patient_reply_for_treatment",
        fail_draft_patient_reply_for_treatment,
    )

    with pytest.raises(RuntimeError):
        await app_client.post(
            f"/internal/treatments/{treatment_id}/process-buffered-patient-turn"
        )

    message = await db_session.scalar(select(ConversationMessage))
    assert message is not None
    assert message.processed_at is None


async def _create_treatment(app_client: AsyncClient, mrn: str) -> UUID:
    response = await app_client.post(
        "/treatments",
        json={
            "patient": {
                "name": "Eleanor Vance",
                "dob": "1955-10-12",
                "mrn": mrn,
                "phone": "+18005551212",
            },
            "treatment": {"clinical_objective": "Monitor recovery"},
            "medications": [
                {
                    "name": "Amoxicillin",
                    "dosage": "500 mg",
                    "frequency": "Three Times Daily (TID)",
                    "duration": "7 days",
                    "objective": None,
                }
            ],
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["treatment_id"])


async def _age_buffered_messages(db_session: AsyncSession, treatment_id: UUID) -> None:
    messages = (
        await db_session.execute(
            select(ConversationMessage).where(ConversationMessage.treatment_id == treatment_id)
        )
    ).scalars().all()
    old_enough = datetime.now(UTC) - timedelta(seconds=10)
    for message in messages:
        message.created_at = old_enough
    await db_session.flush()


def _patch_generated_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_draft_patient_reply_for_treatment(*args: object, **kwargs: object) -> object:
        return PatientReplyDraft(
            message="I will ask your pharmacist to review this before advising further.",
            requires_pharmacist_review=True,
            escalation_reason="side_effect",
            confidence=0.9,
        )

    monkeypatch.setattr(
        "app.api.internal.draft_patient_reply_for_treatment",
        fake_draft_patient_reply_for_treatment,
    )


def _patch_safety_decision(monkeypatch: pytest.MonkeyPatch, treatment_id: UUID) -> None:
    async def fake_review_patient_draft_safety(*args: object, **kwargs: object) -> object:
        assistant_draft = str(kwargs["assistant_draft"])
        return PatientDraftSafetyDecision(
            status="send",
            message_to_send=assistant_draft,
            hold_reason=None,
            review=SafetyReview(
                treatment_id=treatment_id,
                input_guard=GuardResult(
                    stage="input",
                    action="allow",
                    categories=[],
                    rationale="Input allowed.",
                    confidence=0.9,
                ),
                referee=RefereeResult(
                    action="allow",
                    violations=[],
                    rationale="Referee allowed.",
                    confidence=0.9,
                ),
                output_guard=GuardResult(
                    stage="output",
                    action="allow",
                    categories=[],
                    rationale="Output allowed.",
                    confidence=0.9,
                ),
            ),
        )

    monkeypatch.setattr(
        "app.services.conversation_messages.review_patient_draft_safety",
        fake_review_patient_draft_safety,
    )
