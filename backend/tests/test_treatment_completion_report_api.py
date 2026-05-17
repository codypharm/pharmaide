"""GET /treatments/:id/completion-report API contract."""

from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
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


@pytest.mark.usefixtures("postgres_container")
async def test_completion_report_returns_sanitized_counts_for_completed_treatment(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment, medication = await _persist_treatment(db_session, status="completed")
    db_session.add_all(
        [
            AdherenceEvent(
                treatment_id=treatment.id,
                medication_id=medication.id,
                status="taken",
                source="patient",
                note="Patient said they felt dizzy after dose.",
            ),
            PatientCheckIn(
                treatment_id=treatment.id,
                report_type="side_effect",
                source="patient",
                message="I feel dizzy.",
            ),
            TriageItem(
                treatment_id=treatment.id,
                reason="side_effect",
                status="open",
            ),
        ]
    )
    await db_session.flush()

    response = await app_client.get(f"/treatments/{treatment.id}/completion-report")

    assert response.status_code == 200
    body = response.json()
    assert body["treatment_id"] == str(treatment.id)
    assert body["patient_id"] == str(treatment.patient_id)
    assert body["status"] == "completed"
    assert body["medication_count"] == 1
    assert body["adherence"] == {"total_count": 1, "by_status": {"taken": 1}}
    assert body["patient_updates"] == {
        "total_count": 1,
        "by_report_type": {"side_effect": 1},
    }
    assert body["triage"] == {
        "total_count": 1,
        "by_status": {"open": 1},
        "by_reason": {"side_effect": 1},
    }
    assert "dizzy" not in response.text.lower()

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.resource_id == treatment.id,
            AuditLogEntry.event_type == "completion_report_viewed",
        )
    )
    assert audit is not None
    assert audit.resource_type == "treatment"
    assert audit.payload == {
        "report_status": "completed",
        "medication_count": 1,
        "adherence_total_count": 1,
        "patient_update_total_count": 1,
        "triage_total_count": 1,
    }
    assert "dizzy" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_completion_report_returns_404_for_unknown_treatment(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await app_client.get(f"/treatments/{uuid4()}/completion-report")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}
    assert await _audit_count(db_session) == 0


@pytest.mark.usefixtures("postgres_container")
async def test_completion_report_returns_409_before_course_completion(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment, _ = await _persist_treatment(db_session, status="active")

    response = await app_client.get(f"/treatments/{treatment.id}/completion-report")

    assert response.status_code == 409
    assert response.json() == {"detail": {"error": "treatment_not_completed"}}
    assert await _audit_count(db_session) == 0


async def _audit_count(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(AuditLogEntry)
            .where(AuditLogEntry.event_type == "completion_report_viewed")
        )
        or 0
    )


async def _persist_treatment(
    session: AsyncSession,
    *,
    status: str,
) -> tuple[Treatment, Medication]:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=f"COURSE-REPORT-API-{uuid4()}",
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        status=status,
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
