"""Internal queued-message delivery worker endpoint."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, ConversationMessage
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delivery tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_marks_queued_outbound_whatsapp_message_sent_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "DELIVERY-001")
    queued = await app_client.post(
        f"/treatments/{treatment_id}/pharmacist-messages",
        json={"message": "Please continue the current dose."},
    )
    assert queued.status_code == 201, queued.text
    message_id = UUID(queued.json()["id"])

    response = await app_client.post("/internal/message-delivery/run-once")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "processed_count": 1,
        "sent_count": 1,
        "failed_count": 0,
    }

    message = await db_session.get(ConversationMessage, message_id)
    assert message is not None
    assert message.status == "sent"
    assert message.external_message_id == f"internal-delivery:{message_id}"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "conversation_message_delivery_marked_sent"
        )
    )
    assert audit is not None
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message_id),
        "channel": "whatsapp",
        "old_status": "queued",
        "new_status": "sent",
        "external_message_id": f"internal-delivery:{message_id}",
        "provider": "internal-placeholder",
    }
    assert "continue" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_run_message_delivery_returns_zero_when_no_messages_are_queued(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post("/internal/message-delivery/run-once")

    assert response.status_code == 200
    assert response.json() == {
        "processed_count": 0,
        "sent_count": 0,
        "failed_count": 0,
    }


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
