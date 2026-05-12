"""GET /treatments/{id}/analysis endpoint."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Patient, Treatment, TreatmentAnalysis


async def _create_treatment(db_session: AsyncSession, mrn: str) -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        clinical_objective="Monitor for ACE-inhibitor cough",
    )
    db_session.add(treatment)
    await db_session.flush()
    return treatment


@pytest.mark.usefixtures("postgres_container")
async def test_get_treatment_analysis_returns_latest_analysis(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    treatment = await _create_treatment(db_session, "ANALYSIS-GET-001")
    older = TreatmentAnalysis(treatment_id=treatment.id, status="completed")
    latest = TreatmentAnalysis(
        treatment_id=treatment.id,
        status="failed",
        error_text="analysis_timeout",
        result={"degraded": True},
    )
    db_session.add_all([older, latest])
    await db_session.flush()

    response = await app_client.get(f"/treatments/{treatment.id}/analysis")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert UUID(payload["id"]) == latest.id
    assert UUID(payload["treatment_id"]) == treatment.id
    assert payload["status"] == "failed"
    assert payload["result"] == {"degraded": True}
    assert payload["error_text"] == "analysis_timeout"
    assert payload["started_at"] is None
    assert payload["completed_at"] is None
    assert "created_at" in payload


@pytest.mark.usefixtures("postgres_container")
async def test_get_treatment_analysis_returns_204_when_none_exists(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    treatment = await _create_treatment(db_session, "ANALYSIS-GET-002")

    response = await app_client.get(f"/treatments/{treatment.id}/analysis")

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.usefixtures("postgres_container")
async def test_get_treatment_analysis_returns_404_for_missing_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.get(f"/treatments/{uuid4()}/analysis")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}
