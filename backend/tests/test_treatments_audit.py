"""Audit log content — no PHI in payload.

CLAUDE.md: "Audit everything." HIPAA: "minimum necessary." A
treatment_created audit row carries IDs and a non-PHI summary; the
patient's name, DOB, MRN, phone, and dose details stay out.
"""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry


@pytest.mark.usefixtures("postgres_container")
async def test_audit_payload_excludes_phi(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    body = {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": "AUDIT-001",
            "phone": "+18005551212",
        },
        "treatment": {"clinical_objective": "Monitor for cough"},
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
    assert response.status_code == 201
    treatment_id = UUID(response.json()["treatment_id"])

    audit_row = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.resource_id == treatment_id)
        )
    ).scalar_one()

    payload = audit_row.payload

    # Expected non-PHI fields are present and useful for forensics.
    assert payload["medication_count"] == 2
    assert payload["medication_names"] == ["Lisinopril", "Hydrochlorothiazide"]
    assert payload["ingestion_method"] == "structured"
    assert payload["clinical_objective_present"] is True

    # Forbidden fields — anything that could re-identify a patient.
    serialised = str(payload).lower()
    assert "eleanor" not in serialised
    assert "vance" not in serialised
    assert "1955" not in serialised
    assert "audit-001" not in serialised
    assert "+18005551212" not in serialised
    assert "10 mg" not in serialised
    assert "30 days" not in serialised
    assert "monitor for cough" not in serialised
