"""GET /treatments/:id — verification round-trip.

This endpoint exists for curl-based verification of the write path.
Surveillance / Triage dashboard reads land in a later slice.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.mark.usefixtures("postgres_container")
async def test_get_returns_full_lineage_after_create(app_client: AsyncClient) -> None:
    body = {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": "GET-RT-001",
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
            }
        ],
        "ingestion_method": "structured",
    }
    create = await app_client.post("/treatments", json=body)
    assert create.status_code == 201
    treatment_id = create.json()["treatment_id"]

    fetched = await app_client.get(f"/treatments/{treatment_id}")
    assert fetched.status_code == 200
    detail = fetched.json()

    assert detail["patient"]["name"] == "Eleanor Vance"
    assert detail["patient"]["mrn"] == "GET-RT-001"
    assert detail["patient"]["phone"] == "+18005551212"
    assert detail["treatment"]["clinical_objective"] == "Monitor for cough"
    assert detail["treatment"]["status"] == "pending"
    # created_at is needed by the Treatment Detail page header.
    assert isinstance(detail["treatment"]["created_at"], str)
    assert detail["treatment"]["created_at"].endswith("Z") or "+" in detail["treatment"]["created_at"]
    assert len(detail["medications"]) == 1
    assert detail["medications"][0]["name"] == "Lisinopril"
    assert detail["medications"][0]["ordinal"] == 0


@pytest.mark.usefixtures("postgres_container")
async def test_get_returns_404_for_unknown_id(app_client: AsyncClient) -> None:
    response = await app_client.get(f"/treatments/{uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_get_returns_422_for_malformed_uuid(app_client: AsyncClient) -> None:
    response = await app_client.get("/treatments/not-a-uuid")
    assert response.status_code == 422
