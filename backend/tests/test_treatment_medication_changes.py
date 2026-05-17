"""Existing-treatment medication change commands."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, Medication, Treatment, TreatmentAnalysis
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep command tests focused on treatment mutation, not analysis workers."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_medication_pauses_cycle_marks_analysis_stale_and_audits(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-001")
    medication = await _first_medication(db_session, treatment_id)
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="completed",
        result={"clinical_summary": "Ready for monitoring."},
    )
    db_session.add(analysis)
    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    treatment.status = "active"
    treatment.automation_mode = "active"
    await db_session.flush()

    response = await app_client.post(
        f"/treatments/{treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == str(medication.id)
    assert payload["discontinued_at"] is not None

    await db_session.refresh(medication)
    await db_session.refresh(treatment)
    await db_session.refresh(analysis)
    assert medication.discontinued_at is not None
    assert treatment.status == "pending"
    assert treatment.automation_mode == "paused"
    assert analysis.status == "superseded"

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "treatment_medication_discontinued",
            AuditLogEntry.resource_id == medication.id,
        )
    )
    assert audit is not None
    assert audit.resource_type == "medication"
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "medication_id": str(medication.id),
        "old_treatment_status": "active",
        "new_treatment_status": "pending",
        "old_automation_mode": "active",
        "new_automation_mode": "paused",
        "superseded_analysis_count": 2,
        "already_discontinued": False,
    }
    assert "lisinopril" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_discontinue_medication_returns_404_for_wrong_treatment(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-002")
    other_treatment_id = await _create_treatment(app_client, mrn="MED-CHANGE-003")
    medication = await _first_medication(db_session, treatment_id)

    response = await app_client.post(
        f"/treatments/{other_treatment_id}/medications/{medication.id}/discontinue"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "medication_not_found"}}


async def _create_treatment(app_client: AsyncClient, *, mrn: str) -> UUID:
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
                "treatment_start_at": "2026-05-16T08:00:00Z",
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


async def _first_medication(db_session: AsyncSession, treatment_id: UUID) -> Medication:
    medication = await db_session.scalar(
        select(Medication).where(Medication.treatment_id == treatment_id)
    )
    assert medication is not None
    return medication
