"""POST /treatments — MRN uniqueness collision behaviour.

Server enforces UNIQUE on patients.mrn. A second submit reusing an MRN
returns 409 with a sanitised body — the existing patient_id is NOT
leaked (that lands when the search-existing flow ships).
"""

import pytest
from httpx import AsyncClient

VALID_BODY = {
    "patient": {
        "name": "Eleanor Vance",
        "dob": "1955-10-12",
        "mrn": "DUPLICATE-MRN",
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


@pytest.mark.usefixtures("postgres_container")
async def test_duplicate_mrn_returns_409(app_client: AsyncClient) -> None:
    first = await app_client.post("/treatments", json=VALID_BODY)
    assert first.status_code == 201, first.text

    second = await app_client.post("/treatments", json=VALID_BODY)
    assert second.status_code == 409
    assert second.json() == {"detail": {"error": "mrn_already_exists"}}
