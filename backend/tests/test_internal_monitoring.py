"""Internal monitoring worker for active treatment schedules."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import AnalysisResult, ReminderSlot, Schedule
from app.db.models import (
    AdherenceEvent,
    AuditLogEntry,
    ConversationMessage,
    Medication,
    Treatment,
    TreatmentAnalysis,
    TriageItem,
)
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
        await db_session.execute(_reminder_messages_query())
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
async def test_run_treatment_monitoring_completes_course_after_final_reminder_is_queued(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-COMPLETE-001",
    )

    response = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert response.status_code == 200, response.text
    assert response.json() == {"queued_count": 1, "skipped_count": 0}
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.status == "completed"
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "treatment_completed")
    )
    assert audit is not None
    assert audit.resource_id == treatment_id


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_waits_for_future_reminders_without_completing_course(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-FUTURE-001",
        analysis_builder=_analysis_result_with_future_only_reminder,
    )

    response = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert response.status_code == 200, response.text
    assert response.json() == {"queued_count": 0, "skipped_count": 1}
    reminder_count = await db_session.scalar(
        select(func.count()).select_from(_reminder_messages_query().subquery())
    )
    assert reminder_count == 0
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.status == "active"
    completed_audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(AuditLogEntry.event_type == "treatment_completed")
    )
    assert completed_audit_count == 0


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
    assert second.status_code == 409
    assert second.json() == {"detail": {"error": "treatment_not_active"}}
    message_count = await db_session.scalar(
        select(func.count()).select_from(_reminder_messages_query().subquery())
    )
    assert message_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_rejects_pending_treatment(
    app_client: AsyncClient,
) -> None:
    treatment_id = await _create_treatment(app_client, "MONITOR-003")

    response = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "treatment_not_active"}}


@pytest.mark.usefixtures("postgres_container")
async def test_run_due_monitoring_processes_active_automated_treatments_once(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    active_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-004",
    )
    paused_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-005",
    )
    pending_id = await _treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-006",
    )
    paused = await db_session.get(Treatment, paused_id)
    assert paused is not None
    paused.automation_mode = "paused"
    await db_session.flush()

    first = await app_client.post("/internal/monitoring/run-due")
    second = await app_client.post("/internal/monitoring/run-due")

    assert first.status_code == 200, first.text
    assert first.json() == {
        "processed_count": 1,
        "queued_count": 1,
        "skipped_count": 0,
    }
    assert second.status_code == 200, second.text
    assert second.json() == {
        "processed_count": 0,
        "queued_count": 0,
        "skipped_count": 0,
    }

    messages = (await db_session.execute(_reminder_messages_query())).scalars().all()
    assert len(messages) == 1
    assert messages[0].treatment_id == active_id
    assert messages[0].treatment_id not in {paused_id, pending_id}

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(AuditLogEntry.event_type == "monitoring_due_run_completed")
    )
    assert audit_count == 2


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_marks_aged_unanswered_reminder_missed(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-NONRESPONSE-001",
        analysis_builder=_analysis_result_with_future_reminder,
    )
    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    assert first.status_code == 200, first.text

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    assert audit is not None
    audit.created_at = datetime.now(UTC) - timedelta(hours=5)
    await db_session.flush()

    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert second.status_code == 200, second.text
    event = await db_session.scalar(
        select(AdherenceEvent).where(
            AdherenceEvent.treatment_id == treatment_id,
            AdherenceEvent.status == "missed",
            AdherenceEvent.source == "system",
        )
    )
    assert event is not None
    assert event.scheduled_for is not None
    non_response_audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_non_response_recorded")
    )
    assert non_response_audit is not None
    assert non_response_audit.payload["reminder_key"] == audit.payload["reminder_key"]
    assert "lisinopril" not in str(non_response_audit.payload).lower()

    triage_item = await db_session.scalar(
        select(TriageItem).where(
            TriageItem.treatment_id == treatment_id,
            TriageItem.reason == "non_responsive",
            TriageItem.status == "open",
        )
    )
    assert triage_item is not None
    assert str(triage_item.conversation_message_id) == audit.payload["message_id"]
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.status == "active"
    assert treatment.automation_mode == "active"
    assert treatment.chat_response_mode == "pharmacist_takeover"


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_does_not_flag_recent_unanswered_reminder(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-NONRESPONSE-RECENT",
        analysis_builder=_analysis_result_with_future_reminder,
    )
    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    assert first.status_code == 200, first.text

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    assert audit is not None
    audit.created_at = datetime.now(UTC) - timedelta(hours=3, minutes=59)
    await db_session.flush()

    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert second.status_code == 200, second.text
    missed_count = await db_session.scalar(
        select(func.count())
        .select_from(AdherenceEvent)
        .where(AdherenceEvent.treatment_id == treatment_id, AdherenceEvent.status == "missed")
    )
    triage_count = await db_session.scalar(
        select(func.count())
        .select_from(TriageItem)
        .where(TriageItem.treatment_id == treatment_id, TriageItem.reason == "non_responsive")
    )
    assert missed_count == 0
    assert triage_count == 0


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_does_not_duplicate_non_response_triage(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-NONRESPONSE-DEDUP",
        analysis_builder=_analysis_result_with_future_reminder,
    )
    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    assert first.status_code == 200, first.text

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    assert audit is not None
    audit.created_at = datetime.now(UTC) - timedelta(hours=5)
    await db_session.flush()

    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    third = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert second.status_code == 200, second.text
    assert third.status_code == 200, third.text
    missed_count = await db_session.scalar(
        select(func.count())
        .select_from(AdherenceEvent)
        .where(AdherenceEvent.treatment_id == treatment_id, AdherenceEvent.status == "missed")
    )
    triage_count = await db_session.scalar(
        select(func.count())
        .select_from(TriageItem)
        .where(TriageItem.treatment_id == treatment_id, TriageItem.reason == "non_responsive")
    )
    non_response_audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(AuditLogEntry.event_type == "monitoring_non_response_recorded")
    )
    assert missed_count == 1
    assert triage_count == 1
    assert non_response_audit_count == 1


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_does_not_mark_missed_after_patient_reply(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-NONRESPONSE-002",
        analysis_builder=_analysis_result_with_future_reminder,
    )
    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    assert first.status_code == 200, first.text

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    message = await db_session.scalar(select(ConversationMessage))
    assert audit is not None
    assert message is not None
    audit.created_at = datetime.now(UTC) - timedelta(hours=5)
    db_session.add(
        AuditLogEntry(
            event_type="patient_reply_adherence_captured",
            resource_type="conversation_message",
            resource_id=message.id,
            payload={
                "treatment_id": str(treatment_id),
                "inbound_message_id": str(message.id),
                "medication_id": audit.payload["reminder_key"].split(":", maxsplit=1)[0],
                "status": "taken",
                "reminder_key": audit.payload["reminder_key"],
                "reminder_key_present": True,
            },
        )
    )
    await db_session.flush()

    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert second.status_code == 200, second.text
    missed_count = await db_session.scalar(
        select(func.count())
        .select_from(AdherenceEvent)
        .where(
            AdherenceEvent.treatment_id == treatment_id,
            AdherenceEvent.status == "missed",
            AdherenceEvent.source == "system",
        )
    )
    triage_count = await db_session.scalar(
        select(func.count())
        .select_from(TriageItem)
        .where(TriageItem.treatment_id == treatment_id, TriageItem.reason == "non_responsive")
    )
    assert missed_count == 0
    assert triage_count == 0


@pytest.mark.usefixtures("postgres_container")
async def test_run_treatment_monitoring_does_not_flag_when_adherence_already_recorded(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _active_treatment_with_analysis(
        app_client,
        db_session,
        mrn="MONITOR-NONRESPONSE-ADHERENCE",
        analysis_builder=_analysis_result_with_future_reminder,
    )
    medication_id = await _first_medication_id(db_session, treatment_id)
    first = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")
    assert first.status_code == 200, first.text

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "monitoring_message_queued")
    )
    assert audit is not None
    audit.created_at = datetime.now(UTC) - timedelta(hours=5)
    db_session.add(
        AdherenceEvent(
            treatment_id=treatment_id,
            medication_id=medication_id,
            status="taken",
            source="patient",
            scheduled_for=datetime(2020, 1, 1, 8, 0, tzinfo=UTC),
            occurred_at=datetime.now(UTC),
        )
    )
    await db_session.flush()

    second = await app_client.post(f"/internal/treatments/{treatment_id}/run-due-monitoring")

    assert second.status_code == 200, second.text
    missed_count = await db_session.scalar(
        select(func.count())
        .select_from(AdherenceEvent)
        .where(AdherenceEvent.treatment_id == treatment_id, AdherenceEvent.status == "missed")
    )
    triage_count = await db_session.scalar(
        select(func.count())
        .select_from(TriageItem)
        .where(TriageItem.treatment_id == treatment_id, TriageItem.reason == "non_responsive")
    )
    assert missed_count == 0
    assert triage_count == 0


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
    analysis_builder: Callable[[UUID], dict[str, object]] | None = None,
) -> UUID:
    treatment_id = await _create_treatment(app_client, mrn)
    medication_id = await _first_medication_id(db_session, treatment_id)
    build_analysis = analysis_builder or _analysis_result
    db_session.add(
        TreatmentAnalysis(
            treatment_id=treatment_id,
            status="completed",
            result=build_analysis(medication_id),
        )
    )
    await db_session.flush()
    start = await app_client.post(f"/treatments/{treatment_id}/start-cycle")
    assert start.status_code == 200, start.text
    return treatment_id


async def _treatment_with_analysis(
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


def _reminder_messages_query():
    return select(ConversationMessage).where(
        ConversationMessage.direction == "outbound",
        ConversationMessage.sender_type == "assistant",
        ConversationMessage.channel == "whatsapp",
        ConversationMessage.body.like("Reminder:%"),
    )


def _analysis_result_with_future_reminder(medication_id: UUID) -> dict[str, object]:
    return AnalysisResult(
        groundings=[],
        ddi_warnings=[],
        schedule=Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=timedelta(0),
                    human_label="morning dose",
                ),
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=timedelta(days=3650),
                    human_label="future dose",
                ),
            ]
        ),
        reasoning=None,
        degraded=False,
        completed_stages=["schedule"],
    ).model_dump(mode="json")


def _analysis_result_with_future_only_reminder(medication_id: UUID) -> dict[str, object]:
    return AnalysisResult(
        groundings=[],
        ddi_warnings=[],
        schedule=Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=timedelta(days=3650),
                    human_label="tomorrow dose",
                )
            ]
        ),
        reasoning=None,
        degraded=False,
        completed_stages=["schedule"],
    ).model_dump(mode="json")
