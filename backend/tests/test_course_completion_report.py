"""Deterministic end-of-course report foundation."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdherenceEvent,
    Medication,
    Patient,
    PatientCheckIn,
    Treatment,
    TriageItem,
)
from app.services.course_completion_report import TreatmentNotFound, build_course_completion_report


async def test_build_course_completion_report_returns_counts_without_patient_text(
    db_session: AsyncSession,
) -> None:
    treatment, medication = await _persist_completed_treatment(db_session)
    db_session.add_all(
        [
            AdherenceEvent(
                treatment_id=treatment.id,
                medication_id=medication.id,
                status="taken",
                source="patient",
                note="Patient said they felt dizzy after dose.",
            ),
            AdherenceEvent(
                treatment_id=treatment.id,
                medication_id=medication.id,
                status="missed",
                source="patient",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="side_effect",
                source="patient",
                message="I feel dizzy.",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="not_improving",
                source="patient",
                message="I am not getting better.",
            ),
            TriageItem(
                treatment_id=treatment.id,
                reason="side_effect",
                status="resolved",
            ),
            TriageItem(
                treatment_id=treatment.id,
                reason="non_responsive",
                status="open",
            ),
        ]
    )
    await db_session.flush()

    report = await build_course_completion_report(db_session, treatment_id=treatment.id)

    assert report.treatment_id == treatment.id
    assert report.status == "completed"
    assert report.medication_count == 1
    assert report.adherence.total_count == 2
    assert report.adherence.by_status == {"missed": 1, "taken": 1}
    assert report.patient_updates.total_count == 2
    assert report.patient_updates.by_report_type == {
        "not_improving": 1,
        "side_effect": 1,
    }
    assert report.triage.total_count == 2
    assert report.triage.by_status == {"open": 1, "resolved": 1}
    assert report.triage.by_reason == {"non_responsive": 1, "side_effect": 1}
    assert "dizzy" not in report.model_dump_json().lower()


async def test_build_course_completion_report_rejects_missing_treatment(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(TreatmentNotFound):
        await build_course_completion_report(db_session, treatment_id=uuid4())


async def _persist_completed_treatment(
    session: AsyncSession,
) -> tuple[Treatment, Medication]:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn="COURSE-REPORT-001",
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        status="completed",
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
    return treatment, medication
