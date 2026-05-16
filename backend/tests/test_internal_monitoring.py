"""Internal monitoring worker for active treatment schedules."""

from datetime import timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import AnalysisResult, ReminderSlot, Schedule
from app.db.models import AuditLogEntry, ConversationMessage, Medication, TreatmentAnalysis
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monitoring tests seed analysis rows directly."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_queues_due_reminder_message_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "MONITOR-001")
    medication_id = await _first_medication_id(db_session, treatment_id)
    db_session.add(
        TreatmentAnalysis(
            treatment_id=treatment_id,
            status="completed",
            result=_analysis_result(medication_id),
        )
    )
    await db_session.flush()
    start = await app_client.post(f"/treatments/{treatment_id}/start-cycle")
    assert start.status_code == 200, start.text

    response = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert response.status_code == 200, response.text
    assert response.json() == {"queued_count": 1, "skipped_count": 0}

    messages = (
        await db_session.execute(select(ConversationMessage))
    ).scalars().all()
    assert len(messages) == 1
    message = messages[0]
    assert message.treatment_id == treatment_id
    assert message.direction == "outbound"
    assert message.sender_type == "assistant"
    assert message.channel == "whatsapp"
    assert message.status == "queued"
    assert "Lisinopril" in message.body

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    assert audit is not None
    assert audit.resource_type == "conversation_message"
    assert audit.resource_id == message.id
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "message_id": str(message.id),
        "reminder_key": f"{medication_id}:PT0S:morning dose",
        "scheduled_for_present": True,
        "channel": "whatsapp",
        "status": "queued",
    }
    assert "lisinopril" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_does_not_duplicate_existing_reminder_message(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-002",
    )

    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert first.status_code == 200, first.text
    assert first.json() == {"queued_count": 1, "skipped_count": 0}
    assert second.status_code == 200, second.text
    assert second.json() == {"queued_count": 0, "skipped_count": 1}
    message_count = await db_session.scalar(select(func.count()).select_from(ConversationMessage))
    assert message_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_rejects_pending_treatment(
    app_client: AsyncClient,
) -> None:
    treatment_id = await _create_treatment(app_client, "MONITOR-003")

    response = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "treatment_not_active"}}


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
            "treatment": {
                "clinical_objective": "Monitor adherence",
                "treatment_start_at": "2020-01-01T08:00:00Z",
            },
            "medications": [
                {
                    "name": "Lisinopril",
                    "dosage": "10 mg",
                    "frequency": "Once Daily (QD)",
                    "duration": "30 days",
                    "objective": None,
                }
            ],
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201, response.text
    return UUID(response.json()["treatment_id"])


async def _active_treatment_with_analysis(
    app_client: AsyncClient,
    db_session: AsyncSession,
    *,
    mrn: str,
) -> UUID:
    treatment_id = await _create_treatment(app_client, mrn)
    medication_id = await _first_medication_id(db_session, treatment_id)
    db_session.add(
        TreatmentAnalysis(
            treatment_id=treatment_id,
            status="completed",
            result=_analysis_result(medication_id),
        )
    )
    await db_session.flush()
    start = await app_client.post(f"/treatments/{treatment_id}/start-cycle")
    assert start.status_code == 200, start.text
    return treatment_id


async def _first_medication_id(db_session: AsyncSession, treatment_id: UUID) -> UUID:
    medication_id = await db_session.scalar(
        select(Medication.id).where(Medication.treatment_id == treatment_id)
    )
    assert medication_id is not None
    return medication_id


def _analysis_result(medication_id: UUID) -> dict[str, object]:
    return AnalysisResult(
        groundings=[],
        ddi_warnings=[],
        schedule=Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=timedelta(0),
                    human_label="morning dose",
                )
            ]
        ),
        reasoning=None,
        degraded=False,
        completed_stages=["schedule"],
    ).model_dump(mode="json")
