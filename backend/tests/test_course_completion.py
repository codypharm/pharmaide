"""Treatment course completion detection."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import AnalysisResult, ReminderSlot, Schedule
from app.db.models import AuditLogEntry, Medication, Patient, Treatment, TreatmentAnalysis
from app.services.course_completion import complete_treatment_course_if_finished


async def test_complete_treatment_course_marks_active_completed_after_all_reminders_queued(
    db_session: AsyncSession,
) -> None:
    treatment, medication, analysis = await _persist_active_treatment_with_schedule(
        db_session,
        mrn="COURSE-COMPLETE-001",
        offsets=[timedelta(0), timedelta(hours=1)],
    )
    _seed_monitoring_audit(
        db_session,
        treatment_id=treatment.id,
        medication_id=medication.id,
        offset="PT0S",
        human_label="dose 1",
    )
    _seed_monitoring_audit(
        db_session,
        treatment_id=treatment.id,
        medication_id=medication.id,
        offset="PT1H",
        human_label="dose 2",
    )
    await db_session.flush()

    result = await complete_treatment_course_if_finished(
        db_session,
        treatment_id=treatment.id,
        now=datetime(2026, 5, 17, 12, tzinfo=UTC),
    )

    assert result.completed is True
    assert result.reason == "completed"
    await db_session.refresh(treatment)
    assert treatment.status == "completed"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "treatment_completed")
    )
    assert audit is not None
    assert audit.resource_type == "treatment"
    assert audit.resource_id == treatment.id
    assert audit.payload == {
        "old_status": "active",
        "new_status": "completed",
        "analysis_id": str(analysis.id),
        "scheduled_reminder_count": 2,
    }
    assert "lisinopril" not in str(audit.payload).lower()


async def test_complete_treatment_course_waits_for_unqueued_reminders(
    db_session: AsyncSession,
) -> None:
    treatment, medication, _analysis = await _persist_active_treatment_with_schedule(
        db_session,
        mrn="COURSE-COMPLETE-002",
        offsets=[timedelta(0), timedelta(hours=1)],
    )
    _seed_monitoring_audit(
        db_session,
        treatment_id=treatment.id,
        medication_id=medication.id,
        offset="PT0S",
        human_label="dose 1",
    )
    await db_session.flush()

    result = await complete_treatment_course_if_finished(
        db_session,
        treatment_id=treatment.id,
        now=datetime(2026, 5, 17, 12, tzinfo=UTC),
    )

    assert result.completed is False
    assert result.reason == "unqueued_reminders"
    await db_session.refresh(treatment)
    assert treatment.status == "active"
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "treatment_completed")
    )
    assert audit is None


async def _persist_active_treatment_with_schedule(
    session: AsyncSession,
    *,
    mrn: str,
    offsets: list[timedelta],
) -> tuple[Treatment, Medication, TreatmentAnalysis]:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        status="active",
        clinical_objective="Monitor adherence",
        treatment_start_at=datetime(2026, 5, 17, 8, tzinfo=UTC),
    )
    medication = Medication(
        treatment=treatment,
        name="Lisinopril",
        dosage="10 mg",
        frequency="Once Daily (QD)",
        duration="1 day",
        ordinal=0,
    )
    session.add(treatment)
    await session.flush()
    analysis = TreatmentAnalysis(
        treatment_id=treatment.id,
        status="completed",
        result=_analysis_result(medication.id, offsets),
    )
    session.add(analysis)
    await session.flush()
    return treatment, medication, analysis


def _analysis_result(medication_id: UUID, offsets: list[timedelta]) -> dict[str, object]:
    return AnalysisResult(
        groundings=[],
        ddi_warnings=[],
        schedule=Schedule(
            reminders=[
                ReminderSlot(
                    medication_id=medication_id,
                    offset_from_start=offset,
                    human_label=f"dose {index + 1}",
                )
                for index, offset in enumerate(offsets)
            ]
        ),
        reasoning=None,
        degraded=False,
        completed_stages=["schedule"],
    ).model_dump(mode="json")


def _seed_monitoring_audit(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    medication_id: UUID,
    offset: str,
    human_label: str,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="monitoring_message_queued",
            resource_type="conversation_message",
            resource_id=treatment_id,
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(treatment_id),
                "reminder_key": f"{medication_id}:{offset}:{human_label}",
                "scheduled_for_present": True,
                "channel": "whatsapp",
                "status": "queued",
            },
        )
    )
