"""POST /treatments — happy-path lineage creation.

V1 of the Sprint 2 ingestion slice. Asserts that one form submission
creates exactly: 1 patient + 1 treatment + N medications + 1 audit row,
all atomically, and returns the new ids.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, Medication, Patient, Treatment, TreatmentAnalysis
from app.services import task_runner


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatments_creates_full_lineage(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def capture_schedule(coro_fn: object, *args: object, **kwargs: object) -> None:
        scheduled.append((coro_fn, args, kwargs))

    monkeypatch.setattr(task_runner, "schedule", capture_schedule)

    body = {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": "TEST-MRN-001",
            "phone": "+18005551212",
        },
        "treatment": {"clinical_objective": "Monitor for ACE-inhibitor cough"},
        "medications": [
            {
                "name": "Lisinopril",
                "dosage": "10 mg",
                "frequency": "Once Daily (QD)",
                "duration": "30 days",
                "objective": None,
            },
            {
                "name": "Hydrochlorothiazide",
                "dosage": "12.5 mg",
                "frequency": "Once Daily (QD)",
                "duration": "30 days",
                "objective": None,
            },
        ],
        "ingestion_method": "structured",
    }

    response = await app_client.post("/treatments", json=body)

    assert response.status_code == 201, response.text
    payload = response.json()
    assert "treatment_id" in payload
    assert "patient_id" in payload
    assert "analysis_id" in payload

    patient_id = UUID(payload["patient_id"])
    treatment_id = UUID(payload["treatment_id"])
    analysis_id = UUID(payload["analysis_id"])

    patient = await db_session.get(Patient, patient_id)
    assert patient is not None
    assert patient.name == "Eleanor Vance"
    assert patient.mrn == "TEST-MRN-001"
    assert patient.phone == "+18005551212"

    treatment = await db_session.get(Treatment, treatment_id)
    assert treatment is not None
    assert treatment.patient_id == patient_id
    assert treatment.status == "pending"
    assert treatment.clinical_objective == "Monitor for ACE-inhibitor cough"

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.treatment_id == treatment_id
    assert analysis.status == "pending"
    assert len(scheduled) == 1
    assert scheduled[0][1][1] == analysis_id
    assert scheduled[0][2]["checkpoint_db_path"] == "./pharmaide.db"
    assert scheduled[0][2]["rxnorm_base_url"] == "https://rxnav.nlm.nih.gov/REST"
    assert "openai_api_key" in scheduled[0][2]

    meds_result = await db_session.execute(
        select(Medication)
        .where(Medication.treatment_id == treatment_id)
        .order_by(Medication.ordinal)
    )
    meds = list(meds_result.scalars())
    assert [m.name for m in meds] == ["Lisinopril", "Hydrochlorothiazide"]
    assert [m.ordinal for m in meds] == [0, 1]

    audit_result = await db_session.execute(
        select(AuditLogEntry).where(AuditLogEntry.resource_id == treatment_id)
    )
    audits = list(audit_result.scalars())
    assert len(audits) == 1
    assert audits[0].event_type == "treatment_created"
    assert audits[0].resource_type == "treatment"
