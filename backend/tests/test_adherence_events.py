"""Adherence events track what happened to planned medication reminders."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, Medication
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adherence tests create treatments as setup; analysis has separate coverage."""
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
            "treatment": {
                "clinical_objective": "Monitor adherence",
                "treatment_start_at": "2026-05-18T08:00:00Z",
            },
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


async def _first_medication_id(db_session: AsyncSession, treatment_id: UUID) -> UUID:
    medication = await db_session.scalar(
        select(Medication).where(Medication.treatment_id == treatment_id).limit(1)
    )
    assert medication is not None
    return medication.id


@pytest.mark.usefixtures("postgres_container")
async def test_create_adherence_event_records_status_and_audit_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "ADH-001")
    medication_id = await _first_medication_id(db_session, treatment_id)

    response = await app_client.post(
        f"/treatments/{treatment_id}/adherence-events",
        json={
            "medication_id": str(medication_id),
            "status": "taken",
            "source": "patient",
            "scheduled_for": "2026-05-18T08:00:00Z",
            "occurred_at": "2026-05-18T08:05:00Z",
            "note": "  Took after breakfast.  ",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["treatment_id"] == str(treatment_id)
    assert payload["medication_id"] == str(medication_id)
    assert payload["status"] == "taken"
    assert payload["source"] == "patient"
    assert payload["note"] == "Took after breakfast."
    assert payload["scheduled_for"].startswith("2026-05-18T08:00:00")
    assert payload["occurred_at"].startswith("2026-05-18T08:05:00")

    audit = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.resource_id == UUID(payload["id"]))
            .where(AuditLogEntry.event_type == "adherence_event_recorded")
        )
    ).scalar_one()
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "medication_id": str(medication_id),
        "status": "taken",
        "source": "patient",
        "scheduled_for_present": True,
        "occurred_at_present": True,
        "note_present": True,
    }
    assert "breakfast" not in str(audit.payload).lower()


@pytest.mark.usefixtures("postgres_container")
async def test_list_adherence_events_returns_newest_first(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "ADH-002")
    medication_id = await _first_medication_id(db_session, treatment_id)
    for status, occurred_at in [
        ("missed", "2026-05-18T08:00:00Z"),
        ("taken", "2026-05-18T16:00:00Z"),
    ]:
        response = await app_client.post(
            f"/treatments/{treatment_id}/adherence-events",
            json={
                "medication_id": str(medication_id),
                "status": status,
                "source": "patient",
                "occurred_at": occurred_at,
            },
        )
        assert response.status_code == 201

    response = await app_client.get(f"/treatments/{treatment_id}/adherence-events")

    assert response.status_code == 200
    assert [item["status"] for item in response.json()["items"][:2]] == ["taken", "missed"]


@pytest.mark.usefixtures("postgres_container")
async def test_adherence_event_rejects_medication_from_another_treatment(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "ADH-003")
    other_treatment_id = await _create_treatment(app_client, "ADH-004")
    other_medication_id = await _first_medication_id(db_session, other_treatment_id)

    response = await app_client.post(
        f"/treatments/{treatment_id}/adherence-events",
        json={
            "medication_id": str(other_medication_id),
            "status": "taken",
            "source": "patient",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "medication_not_found"}}


@pytest.mark.usefixtures("postgres_container")
async def test_adherence_event_rejects_naive_event_times(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment_id = await _create_treatment(app_client, "ADH-005")
    medication_id = await _first_medication_id(db_session, treatment_id)

    response = await app_client.post(
        f"/treatments/{treatment_id}/adherence-events",
        json={
            "medication_id": str(medication_id),
            "status": "held",
            "source": "pharmacist",
            "scheduled_for": "2026-05-18T08:00:00",
        },
    )

    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_adherence_events_return_404_for_unknown_treatment(app_client: AsyncClient) -> None:
    missing_id = uuid4()

    create = await app_client.post(
        f"/treatments/{missing_id}/adherence-events",
        json={"medication_id": str(uuid4()), "status": "taken", "source": "patient"},
    )
    listing = await app_client.get(f"/treatments/{missing_id}/adherence-events")

    assert create.status_code == 404
    assert create.json() == {"detail": {"error": "treatment_not_found"}}
    assert listing.status_code == 404
    assert listing.json() == {"detail": {"error": "treatment_not_found"}}
