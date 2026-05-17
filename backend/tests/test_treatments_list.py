"""GET /treatments — paginated list endpoint.

Returns lean summary rows (no full medication list) so dashboard pages
can render a queue/feed view without per-row roundtrips.
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Treatment
from app.services import task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """List tests create rows as setup; analysis execution is covered elsewhere."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


def _body(mrn: str, name: str, med_name: str, objective: str | None = None) -> dict:
    return {
        "patient": {
            "name": name,
            "dob": "1955-10-12",
            "mrn": mrn,
            "phone": "+18005551212",
        },
        "treatment": {
            "clinical_objective": objective,
            "treatment_start_at": "2026-05-16T08:30:00Z",
        },
        "medications": [
            {
                "name": med_name,
                "dosage": "10 mg",
                "frequency": "Once Daily (QD)",
                "duration": "30 days",
                "objective": None,
            }
        ],
        "ingestion_method": "structured",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_list_returns_lean_summary_rows(app_client: AsyncClient) -> None:
    create = await app_client.post(
        "/treatments", json=_body("LIST-001", "Eleanor Vance", "Lisinopril")
    )
    assert create.status_code == 201

    response = await app_client.get("/treatments")
    assert response.status_code == 200
    body = response.json()

    assert "items" in body
    assert len(body["items"]) >= 1
    row = next(r for r in body["items"] if r["patient"]["mrn"] == "LIST-001")
    assert row["treatment"]["status"] == "pending"
    assert row["treatment"]["treatment_start_at"].startswith("2026-05-16T08:30:00")
    assert isinstance(row["treatment"]["created_at"], str)
    assert row["patient"]["name"] == "Eleanor Vance"
    # Lean: no nested medications array, just count + first-name preview.
    assert "medications" not in row
    assert row["medication_count"] == 1
    assert row["first_medication_name"] == "Lisinopril"


@pytest.mark.usefixtures("postgres_container")
async def test_list_orders_newest_first(app_client: AsyncClient) -> None:
    for i in range(3):
        await app_client.post(
            "/treatments", json=_body(f"ORDER-{i:03d}", f"Patient {i}", "Lisinopril")
        )

    response = await app_client.get("/treatments")
    assert response.status_code == 200
    items = response.json()["items"]
    mrns = [r["patient"]["mrn"] for r in items if r["patient"]["mrn"].startswith("ORDER-")]
    # Reverse-chronological: ORDER-002 was created last → appears first.
    assert mrns[:3] == ["ORDER-002", "ORDER-001", "ORDER-000"]


@pytest.mark.usefixtures("postgres_container")
async def test_list_respects_limit_and_offset(app_client: AsyncClient) -> None:
    for i in range(5):
        await app_client.post(
            "/treatments", json=_body(f"PAGE-{i:03d}", f"Patient {i}", "Lisinopril")
        )

    page_1 = (await app_client.get("/treatments", params={"limit": 2, "offset": 0})).json()
    page_2 = (await app_client.get("/treatments", params={"limit": 2, "offset": 2})).json()

    assert len(page_1["items"]) == 2
    assert len(page_2["items"]) == 2
    # Pages must be disjoint.
    page_1_ids = {r["treatment"]["id"] for r in page_1["items"]}
    page_2_ids = {r["treatment"]["id"] for r in page_2["items"]}
    assert page_1_ids.isdisjoint(page_2_ids)


@pytest.mark.usefixtures("postgres_container")
async def test_list_filters_by_status_and_archived_state(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    pending = await app_client.post(
        "/treatments", json=_body("FILTER-001", "Pending Patient", "Lisinopril")
    )
    completed = await app_client.post(
        "/treatments", json=_body("FILTER-002", "Completed Patient", "Amoxicillin")
    )
    archived = await app_client.post(
        "/treatments", json=_body("FILTER-003", "Archived Patient", "Ibuprofen")
    )
    assert pending.status_code == 201
    assert completed.status_code == 201
    assert archived.status_code == 201

    completed_row = await db_session.get(Treatment, completed.json()["treatment_id"])
    archived_row = await db_session.get(Treatment, archived.json()["treatment_id"])
    assert completed_row is not None
    assert archived_row is not None
    completed_row.status = "completed"
    archived_row.status = "completed"
    archived_row.archived_at = datetime.now(UTC)
    await db_session.flush()

    completed_response = await app_client.get(
        "/treatments", params={"status": "completed", "archived": "false"}
    )
    archived_response = await app_client.get("/treatments", params={"archived": "true"})

    assert completed_response.status_code == 200
    completed_mrns = {item["patient"]["mrn"] for item in completed_response.json()["items"]}
    assert "FILTER-002" in completed_mrns
    assert "FILTER-003" not in completed_mrns

    assert archived_response.status_code == 200
    archived_mrns = {item["patient"]["mrn"] for item in archived_response.json()["items"]}
    assert archived_mrns == {"FILTER-003"}


@pytest.mark.usefixtures("postgres_container")
async def test_list_rejects_limit_above_max(app_client: AsyncClient) -> None:
    response = await app_client.get("/treatments", params={"limit": 500})
    assert response.status_code == 422


@pytest.mark.usefixtures("postgres_container")
async def test_list_returns_empty_items_when_no_treatments(app_client: AsyncClient) -> None:
    response = await app_client.get("/treatments")
    assert response.status_code == 200
    assert response.json() == {"items": []}
