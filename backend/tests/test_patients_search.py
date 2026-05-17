"""GET /patients — existing-patient lookup for treatment attachment."""

import pytest
from httpx import AsyncClient

from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patient search tests create treatments only to seed patient rows."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


def _body(mrn: str, name: str, phone: str) -> dict:
    return {
        "patient": {
            "name": name,
            "dob": "1955-10-12",
            "mrn": mrn,
            "phone": phone,
            "allergies": ["Sulfa"],
        },
        "treatment": {
            "clinical_objective": "Monitor symptoms",
            "treatment_start_at": "2026-05-16T08:30:00Z",
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
    }


@pytest.mark.usefixtures("postgres_container")
async def test_search_patients_by_name_mrn_or_phone(app_client: AsyncClient) -> None:
    first = await app_client.post(
        "/treatments",
        json=_body("PAT-SEARCH-001", "Eleanor Vance", "+18005550101"),
    )
    second = await app_client.post(
        "/treatments",
        json=_body("PAT-SEARCH-002", "Marcus Chen", "+18005550202"),
    )
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text

    by_name = await app_client.get("/patients", params={"query": "eleanor"})
    by_mrn = await app_client.get("/patients", params={"query": "SEARCH-002"})
    by_phone = await app_client.get("/patients", params={"query": "550101"})

    assert by_name.status_code == 200
    assert [item["mrn"] for item in by_name.json()["items"]] == ["PAT-SEARCH-001"]

    assert by_mrn.status_code == 200
    assert [item["name"] for item in by_mrn.json()["items"]] == ["Marcus Chen"]

    assert by_phone.status_code == 200
    phone_match = by_phone.json()["items"][0]
    assert phone_match["name"] == "Eleanor Vance"
    assert phone_match["phone"] == "+18005550101"
    assert phone_match["allergies"] == ["Sulfa"]


@pytest.mark.usefixtures("postgres_container")
async def test_search_patients_rejects_blank_query(app_client: AsyncClient) -> None:
    response = await app_client.get("/patients", params={"query": "   "})

    assert response.status_code == 422
