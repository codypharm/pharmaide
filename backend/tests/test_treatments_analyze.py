"""POST /treatments/{id}/analyze endpoint."""

from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, TreatmentAnalysis
from app.services import task_runner


def _treatment_body(mrn: str) -> dict[str, object]:
    return {
        "patient": {
            "name": "Eleanor Vance",
            "dob": "1955-10-12",
            "mrn": mrn,
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
            }
        ],
        "ingestion_method": "structured",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_starts_analysis(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[tuple[object, tuple[object, ...]]] = []

    def capture_schedule(coro_fn: object, *args: object) -> None:
        scheduled.append((coro_fn, args))

    monkeypatch.setattr(task_runner, "schedule", capture_schedule)

    create_response = await app_client.post("/treatments", json=_treatment_body("ANALYZE-001"))
    assert create_response.status_code == 201
    treatment_id = UUID(create_response.json()["treatment_id"])

    response = await app_client.post(f"/treatments/{treatment_id}/analyze")

    assert response.status_code == 202, response.text
    analysis_id = UUID(response.json()["analysis_id"])

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.treatment_id == treatment_id
    assert analysis.status == "pending"
    assert len(scheduled) == 1
    assert scheduled[0][1][1] == analysis_id
    assert scheduled[0][1][2] == 60


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_passes_timeout_override(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[tuple[object, tuple[object, ...]]] = []

    def capture_schedule(coro_fn: object, *args: object) -> None:
        scheduled.append((coro_fn, args))

    monkeypatch.setattr(task_runner, "schedule", capture_schedule)

    create_response = await app_client.post("/treatments", json=_treatment_body("ANALYZE-004"))
    assert create_response.status_code == 201
    treatment_id = UUID(create_response.json()["treatment_id"])

    response = await app_client.post(f"/treatments/{treatment_id}/analyze?timeout=12")

    assert response.status_code == 202, response.text
    assert len(scheduled) == 1
    assert scheduled[0][1][2] == 12


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_background_task_starts_analysis(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    create_response = await app_client.post("/treatments", json=_treatment_body("ANALYZE-003"))
    assert create_response.status_code == 201
    treatment_id = UUID(create_response.json()["treatment_id"])

    response = await app_client.post(f"/treatments/{treatment_id}/analyze")
    assert response.status_code == 202, response.text
    analysis_id = UUID(response.json()["analysis_id"])

    await task_runner.drain()

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "running"
    assert analysis.started_at is not None

    audit = (
        await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.resource_id == treatment_id,
                AuditLogEntry.event_type == "analysis_started",
            )
        )
    ).scalar_one()
    assert audit.payload == {
        "treatment_id": str(treatment_id),
        "analysis_id": str(analysis_id),
    }


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_rejects_duplicate_active_analysis(
    app_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_runner, "schedule", lambda *_args: None)

    create_response = await app_client.post("/treatments", json=_treatment_body("ANALYZE-002"))
    assert create_response.status_code == 201
    treatment_id = UUID(create_response.json()["treatment_id"])

    first_response = await app_client.post(f"/treatments/{treatment_id}/analyze")
    assert first_response.status_code == 202

    second_response = await app_client.post(f"/treatments/{treatment_id}/analyze")

    assert second_response.status_code == 409
    assert second_response.json() == {"detail": {"error": "analysis_in_progress"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_returns_404_for_missing_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(f"/treatments/{uuid4()}/analyze")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}
