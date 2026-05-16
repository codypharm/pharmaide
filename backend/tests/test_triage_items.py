"""Pharmacist triage queue status transitions."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.db.models import AuditLogEntry, ConversationMessage, TriageItem
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Triage tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_patch_triage_item_acknowledges_open_item_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-001")

    response = await app_client.patch(
        f"/triage/items/{item_id}",
        json={"status": "acknowledged"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(item_id)
    assert payload["status"] == "acknowledged"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "triage_item_status_changed")
    )
    assert audit is not None
    assert audit.payload == {
        "old_status": "open",
        "new_status": "acknowledged",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_patch_triage_item_resolves_acknowledged_item(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-002")
    acknowledged = await app_client.patch(
        f"/triage/items/{item_id}",
        json={"status": "acknowledged"},
    )

    response = await app_client.patch(
        f"/triage/items/{item_id}",
        json={"status": "resolved"},
    )

    assert acknowledged.status_code == 200, acknowledged.text
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "resolved"


@pytest.mark.usefixtures("postgres_container")
async def test_patch_triage_item_rejects_invalid_transition(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-003")
    await app_client.patch(f"/triage/items/{item_id}", json={"status": "acknowledged"})
    await app_client.patch(f"/triage/items/{item_id}", json={"status": "resolved"})

    response = await app_client.patch(
        f"/triage/items/{item_id}",
        json={"status": "open"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "invalid_triage_transition"}}


@pytest.mark.usefixtures("postgres_container")
async def test_patch_triage_item_returns_404_for_unknown_item(app_client: AsyncClient) -> None:
    response = await app_client.patch(
        f"/triage/items/{uuid4()}",
        json={"status": "acknowledged"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "triage_item_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_approve_marks_held_draft_approved_and_resolves(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-APPROVE-001")

    response = await app_client.post(f"/triage/items/{item_id}/approve")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["triage_item"]["id"] == str(item_id)
    assert payload["triage_item"]["status"] == "resolved"
    assert payload["approved_message"]["status"] == "approved"
    assert payload["approved_message"]["body"] == "This draft must be reviewed."

    message = await db_session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.id == UUID(payload["approved_message"]["id"])
        )
    )
    assert message is not None
    assert message.status == "approved"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "triage_item_draft_approved")
    )
    assert audit is not None
    assert audit.payload == {
        "triage_item_id": str(item_id),
        "treatment_id": payload["triage_item"]["treatment_id"],
        "approved_message_id": payload["approved_message"]["id"],
        "old_message_status": "held_for_review",
        "new_message_status": "approved",
        "old_triage_status": "open",
        "new_triage_status": "resolved",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_approve_rejects_resolved_item(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-APPROVE-002")
    approved = await app_client.post(f"/triage/items/{item_id}/approve")

    response = await app_client.post(f"/triage/items/{item_id}/approve")

    assert approved.status_code == 200, approved.text
    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "invalid_triage_transition"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_approve_rejects_item_without_held_draft(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "TRIAGE-APPROVE-003")
    item = TriageItem(
        treatment_id=treatment_id,
        conversation_message_id=None,
        reason="non_responsive",
        status="open",
    )
    db_session.add(item)
    await db_session.flush()

    response = await app_client.post(f"/triage/items/{item.id}/approve")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "triage_draft_not_approvable"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_reject_marks_held_draft_rejected_and_resolves(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-REJECT-001")

    response = await app_client.post(f"/triage/items/{item_id}/reject")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["triage_item"]["id"] == str(item_id)
    assert payload["triage_item"]["status"] == "resolved"
    assert payload["rejected_message"]["status"] == "rejected"
    assert payload["rejected_message"]["body"] == "This draft must be reviewed."

    message = await db_session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.id == UUID(payload["rejected_message"]["id"])
        )
    )
    assert message is not None
    assert message.status == "rejected"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "triage_item_draft_rejected")
    )
    assert audit is not None
    assert audit.payload == {
        "triage_item_id": str(item_id),
        "treatment_id": payload["triage_item"]["treatment_id"],
        "rejected_message_id": payload["rejected_message"]["id"],
        "old_message_status": "held_for_review",
        "new_message_status": "rejected",
        "old_triage_status": "open",
        "new_triage_status": "resolved",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_queue_delivery_marks_approved_draft_queued_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-QUEUE-001")
    approved = await app_client.post(f"/triage/items/{item_id}/approve")
    assert approved.status_code == 200, approved.text

    response = await app_client.post(f"/triage/items/{item_id}/queue-delivery")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["triage_item"]["id"] == str(item_id)
    assert payload["triage_item"]["status"] == "resolved"
    assert payload["queued_message"]["status"] == "queued"
    assert payload["queued_message"]["body"] == "This draft must be reviewed."

    message = await db_session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.id == UUID(payload["queued_message"]["id"])
        )
    )
    assert message is not None
    assert message.status == "queued"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "triage_item_draft_queued_for_delivery"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "triage_item_id": str(item_id),
        "treatment_id": payload["triage_item"]["treatment_id"],
        "queued_message_id": payload["queued_message"]["id"],
        "old_message_status": "approved",
        "new_message_status": "queued",
        "triage_status": "resolved",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_triage_item_queue_delivery_rejects_unapproved_draft(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = await _create_open_triage_item(app_client, monkeypatch, "TRIAGE-QUEUE-002")

    response = await app_client.post(f"/triage/items/{item_id}/queue-delivery")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "triage_draft_not_queueable"}}


async def _create_open_triage_item(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    mrn: str,
) -> UUID:
    treatment_id = await _create_treatment(app_client, mrn)
    _patch_safety_decision(monkeypatch, treatment_id, status="hold_for_pharmacist")
    response = await app_client.post(
        f"/treatments/{treatment_id}/conversation-turns",
        json={
            "patient_message": "Can I take an extra dose?",
            "assistant_draft": "This draft must be reviewed.",
            "prescription_context": "Amoxicillin 500 mg three times daily.",
        },
    )
    assert response.status_code == 201, response.text
    triage = await app_client.get("/triage/items")
    assert triage.status_code == 200, triage.text
    return UUID(triage.json()["items"][0]["id"])


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
    assert response.status_code == 201
    return UUID(response.json()["treatment_id"])


def _patch_safety_decision(
    monkeypatch: pytest.MonkeyPatch,
    treatment_id: UUID,
    *,
    status: str,
) -> None:
    async def fake_review_patient_draft_safety(*args: object, **kwargs: object) -> object:
        assistant_draft = str(kwargs["assistant_draft"])
        return _safety_decision(treatment_id, status=status, assistant_draft=assistant_draft)

    monkeypatch.setattr(
        "app.services.conversation_messages.review_patient_draft_safety",
        fake_review_patient_draft_safety,
    )


def _safety_decision(
    treatment_id: UUID,
    *,
    status: str,
    assistant_draft: str,
) -> PatientDraftSafetyDecision:
    return PatientDraftSafetyDecision(
        status=status,
        message_to_send=assistant_draft if status == "send" else None,
        hold_reason=None if status == "send" else "input_guard",
        review=SafetyReview(
            treatment_id=treatment_id,
            input_guard=GuardResult(
                stage="input",
                action="block",
                categories=["unsafe_medical_advice"],
                rationale="Input guard decision.",
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
                rationale="Output guard allowed.",
                confidence=0.9,
            ),
        ),
    )
