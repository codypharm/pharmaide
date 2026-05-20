"""Clinical reporting evaluation cases for completed treatment courses.

End-of-course reports are allowed to summarize operational facts: adherence
counts, patient-update categories, and triage counts. They must not turn those
facts into unsupported clinical outcomes or expose raw patient narratives.
"""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AdherenceEvent,
    AuditLogEntry,
    Medication,
    Patient,
    PatientCheckIn,
    Treatment,
    TriageItem,
)

pytestmark = [pytest.mark.clinical_eval, pytest.mark.usefixtures("postgres_container")]


async def test_course_completion_report_eval_returns_counts_without_clinical_story(
    app_client: AsyncClient,
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
                note="Patient said the rash improved after breakfast.",
            ),
            AdherenceEvent(
                treatment_id=treatment.id,
                medication_id=medication.id,
                status="missed",
                source="patient",
                note="Patient missed the evening tablet after vomiting.",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="side_effect",
                source="patient",
                message="I have severe stomach pain and a rash.",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="not_improving",
                source="patient",
                message="The infection is not getting better.",
            ),
            TriageItem(
                treatment_id=treatment.id,
                reason="side_effect",
                status="resolved",
            ),
        ]
    )
    await db_session.flush()

    response = await app_client.get(f"/treatments/{treatment.id}/completion-report")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "completed"
    assert body["medication_count"] == 1
    assert body["adherence"] == {"total_count": 2, "by_status": {"missed": 1, "taken": 1}}
    assert body["patient_updates"] == {
        "total_count": 2,
        "by_report_type": {"not_improving": 1, "side_effect": 1},
    }
    assert body["triage"] == {
        "total_count": 1,
        "by_status": {"resolved": 1},
        "by_reason": {"side_effect": 1},
    }

    serialized = response.text.lower()
    assert "rash" not in serialized
    assert "vomiting" not in serialized
    assert "infection is not getting better" not in serialized
    assert "amoxicillin" not in serialized
    assert "cured" not in serialized
    assert "recovered" not in serialized


async def test_course_completion_report_eval_audits_aggregate_metadata_only(
    app_client: AsyncClient,
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
                note="Patient described private symptoms in detail.",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="general_update",
                source="patient",
                message="Private family and symptom context.",
            ),
        ]
    )
    await db_session.flush()

    response = await app_client.get(f"/treatments/{treatment.id}/completion-report")

    assert response.status_code == 200, response.text
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "completion_report_viewed",
            AuditLogEntry.resource_id == treatment.id,
        )
    )
    assert audit is not None
    assert audit.payload == {
        "report_status": "completed",
        "medication_count": 1,
        "adherence_total_count": 1,
        "patient_update_total_count": 1,
        "triage_total_count": 0,
    }
    serialized_payload = str(audit.payload).lower()
    assert "private symptoms" not in serialized_payload
    assert "private family" not in serialized_payload
    assert "amoxicillin" not in serialized_payload


async def test_course_completion_report_eval_rejects_unfinished_course_without_audit(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment, _ = await _persist_active_treatment(db_session)

    response = await app_client.get(f"/treatments/{treatment.id}/completion-report")

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": {"error": "treatment_not_completed"}}
    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "completion_report_viewed",
            AuditLogEntry.resource_id == treatment.id,
        )
    )
    assert audit is None


async def _persist_completed_treatment(
    session: AsyncSession,
) -> tuple[Treatment, Medication]:
    return await _persist_treatment(session, status="completed")


async def _persist_active_treatment(
    session: AsyncSession,
) -> tuple[Treatment, Medication]:
    return await _persist_treatment(session, status="active")


async def _persist_treatment(
    session: AsyncSession,
    *,
    status: str,
) -> tuple[Treatment, Medication]:
    patient = Patient(
        name="Report Eval Patient",
        dob=date(1968, 2, 8),
        mrn=f"COURSE-REPORT-EVAL-{uuid4()}",
        phone="+18005550177",
    )
    treatment = Treatment(
        patient=patient,
        status=status,
        clinical_objective="Monitor treatment completion and patient-reported concerns.",
        treatment_start_at=datetime(2026, 5, 17, 8, tzinfo=UTC),
    )
    medication = Medication(
        treatment=treatment,
        name="Amoxicillin",
        dosage="500 mg",
        frequency="Three Times Daily (TID)",
        duration="7 days",
        ordinal=0,
    )
    session.add(treatment)
    await session.flush()
    return treatment, medication
