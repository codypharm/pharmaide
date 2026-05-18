"""Internal worker seam for queued treatment analysis jobs."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Patient, Treatment, TreatmentAnalysis


@pytest.mark.usefixtures("postgres_container")
async def test_run_analysis_worker_executes_analysis_job(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    analysis = await _create_pending_analysis(db_session)
    seen: dict[str, object] = {}

    async def fake_analyze_treatment(
        session_factory: async_sessionmaker[AsyncSession],
        analysis_id: UUID,
        timeout_seconds: int,
        **kwargs: object,
    ) -> None:
        seen["analysis_id"] = analysis_id
        seen["timeout_seconds"] = timeout_seconds
        seen["kwargs"] = kwargs
        async with session_factory() as session, session.begin():
            row = await session.get(TreatmentAnalysis, analysis_id)
            assert row is not None
            row.status = "completed"
            row.result = {"degraded": False, "completed_stages": []}

    monkeypatch.setattr("app.api.internal.analyze_treatment", fake_analyze_treatment)
    kb_scope_id = uuid4()

    response = await app_client.post(
        f"/internal/analyses/{analysis.id}/run",
        json={"kb_scope_id": str(kb_scope_id), "timeout_seconds": 12},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "analysis_id": str(analysis.id),
        "status": "completed",
    }
    assert seen["analysis_id"] == analysis.id
    assert seen["timeout_seconds"] == 12
    kwargs = seen["kwargs"]
    assert isinstance(kwargs, dict)
    assert kwargs["checkpoint_db_path"] == "./pharmaide.db"
    assert kwargs["rxnorm_base_url"] == "https://rxnav.nlm.nih.gov/REST"
    assert kwargs["kb_scope_id"] == kb_scope_id


@pytest.mark.usefixtures("postgres_container")
async def test_run_analysis_worker_returns_404_for_unknown_analysis(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(f"/internal/analyses/{uuid4()}/run")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "analysis_not_found"}}


async def _create_pending_analysis(db_session: AsyncSession) -> TreatmentAnalysis:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=f"INTERNAL-ANALYSIS-{uuid4()}",
        phone="+18005551212",
    )
    db_session.add(patient)
    await db_session.flush()

    treatment = Treatment(
        patient_id=patient.id,
        clinical_objective="Monitor recovery",
    )
    db_session.add(treatment)
    await db_session.flush()

    analysis = TreatmentAnalysis(treatment_id=treatment.id, status="pending")
    db_session.add(analysis)
    await db_session.flush()
    return analysis
