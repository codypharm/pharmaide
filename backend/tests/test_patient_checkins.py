"""Patient check-ins capture clinical status, not just adherence.

These endpoints are the write/read seam for WhatsApp or pharmacist-entered
patient updates such as side effects, not improving, feeling better, and
missed doses.
"""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check-in tests create treatments as setup; analysis has separate coverage."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


async def _create_treatment(app_client: AsyncClient, mrn: str) -> UUID:
    response = await app_client.post(
        "/treatments",
        json={
            "patient": {
                "name": "Eleanor Vance",
                "dob": "1955-10-12",
                "mrn": mrn,
                "phone": "+18005551212",
            },
            "treatment": {"clinical_objective": "Monitor recovery"},
            "medications": [
                {
                    "name": "Amoxicillin",
                    "dosage": "500 mg",
                    "frequency": "Three Times Daily (TID)",
                    "duration": "7 days",
                    "objective": None,
                }
            ],
            "ingestion_method": "structured",
        },
    )
    assert response.status_code == 201
    return UUID(response.json()["treatment_id"])


@pytest.mark.usefixtures("postgres_container")
async def test_create_patient_check_in_records_status_and_audit_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "CHECKIN-001")

    response = await app_client.post(
        f"/treatments/{treatment_id}/check-ins",
        json={
            "report_type": "not_improving",
            "source": "patient",
            "message": "  I am not feeling better after three days.  ",
            "observed_at": "2026-05-18T09:15:00Z",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["treatment_id"] == str(treatment_id)
    assert payload["report_type"] == "not_improving"
    assert payload["source"] == "patient"
    assert payload["message"] == "I am not feeling better after three days."
    assert payload["observed_at"].startswith("2026-05-18T09:15:00")

    audit = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.resource_id == UUID(payload["id"]))
            .where(AuditLogEntry.event_type == "patient_check_in_recorded")
        )
    ).scalar_one()
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "report_type": "not_improving",
        "source": "patient",
        "observed_at_present": True,
    }
    assert "feeling better" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_list_patient_check_ins_returns_newest_first(app_client: AsyncClient) -> None:
    treatment_id = await _create_treatment(app_client, "CHECKIN-002")
    for report_type, message in [
        ("general_update", "First update"),
        ("side_effect", "Second update"),
    ]:
        response = await app_client.post(
            f"/treatments/{treatment_id}/check-ins",
            json={"report_type": report_type, "source": "patient", "message": message},
        )
        assert response.status_code == 201

    response = await app_client.get(f"/treatments/{treatment_id}/check-ins")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["message"] for item in items[:2]] == ["Second update", "First update"]


@pytest.mark.usefixtures("postgres_container")
async def test_patient_check_in_supports_missed_dose_without_becoming_adherence_state(
    app_client: AsyncClient,
) -> None:
    treatment_id = await _create_treatment(app_client, "CHECKIN-003")

    response = await app_client.post(
        f"/treatments/{treatment_id}/check-ins",
        json={
            "report_type": "missed_dose",
            "source": "patient",
            "message": "I missed my afternoon dose yesterday.",
        },
    )

    assert response.status_code == 201
    assert response.json()["report_type"] == "missed_dose"


@pytest.mark.usefixtures("postgres_container")
async def test_patient_check_in_rejects_blank_message(app_client: AsyncClient) -> None:
    treatment_id = await _create_treatment(app_client, "CHECKIN-004")

    response = await app_client.post(
        f"/treatments/{treatment_id}/check-ins",
        json={"report_type": "general_update", "source": "patient", "message": "   "},
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_patient_check_in_rejects_naive_observed_at(app_client: AsyncClient) -> None:
    treatment_id = await _create_treatment(app_client, "CHECKIN-005")

    response = await app_client.post(
        f"/treatments/{treatment_id}/check-ins",
        json={
            "report_type": "side_effect",
            "source": "patient",
            "message": "Dizziness after dose.",
            "observed_at": "2026-05-18T09:15:00",
        },
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_patient_check_ins_return_404_for_unknown_treatment(
    app_client: AsyncClient,
) -> None:
    missing_id = uuid4()

    create = await app_client.post(
        f"/treatments/{missing_id}/check-ins",
        json={"report_type": "general_update", "source": "patient", "message": "Hello"},
    )
    listing = await app_client.get(f"/treatments/{missing_id}/check-ins")

    assert create.status_code == 404
    assert create.json() == {"detail": {"error": "treatment_not_found"}}
    assert listing.status_code == 404
    assert listing.json() == {"detail": {"error": "treatment_not_found"}}
