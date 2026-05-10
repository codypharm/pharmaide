"""POST /treatments — validation enforcement.

Pydantic on the wire — required fields, length bounds, E.164 phone,
non-empty medication list. Each case asserts 422 + a recognisable
error path so the frontend can map errors back to fields inline.
"""

from typing import Any

import pytest
from httpx import AsyncClient


def _base() -> dict[str, Any]:
    return {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": "VAL-001",
            "phone": "+18005551212",
        },
        "treatment": {"clinical_objective": None},
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


def _error_locs(response_json: dict[str, Any]) -> list[tuple[str, ...]]:
    return [tuple(err["loc"]) for err in response_json["detail"]]


@pytest.mark.usefixtures("postgres_container")
async def test_empty_medication_list_rejected(app_client: AsyncClient) -> None:
    body = _base()
    body["medications"] = []
    response = await app_client.post("/treatments", json=body)
    assert response.status_code == 422
    assert ("body", "medications") in _error_locs(response.json())


@pytest.mark.usefixtures("postgres_container")
async def test_missing_phone_rejected(app_client: AsyncClient) -> None:
    body = _base()
    del body["patient"]["phone"]
    response = await app_client.post("/treatments", json=body)
    assert response.status_code == 422
    assert ("body", "patient", "phone") in _error_locs(response.json())


@pytest.mark.usefixtures("postgres_container")
async def test_invalid_phone_rejected(app_client: AsyncClient) -> None:
    body = _base()
    body["patient"]["phone"] = "not-a-phone"
    response = await app_client.post("/treatments", json=body)
    assert response.status_code == 422
    assert ("body", "patient", "phone") in _error_locs(response.json())


@pytest.mark.usefixtures("postgres_container")
async def test_empty_patient_name_rejected(app_client: AsyncClient) -> None:
    body = _base()
    body["patient"]["name"] = ""
    response = await app_client.post("/treatments", json=body)
    assert response.status_code == 422
    assert ("body", "patient", "name") in _error_locs(response.json())


@pytest.mark.usefixtures("postgres_container")
async def test_unknown_ingestion_method_rejected(app_client: AsyncClient) -> None:
    body = _base()
    body["ingestion_method"] = "telepathy"
    response = await app_client.post("/treatments", json=body)
    assert response.status_code == 422
    assert ("body", "ingestion_method") in _error_locs(response.json())
