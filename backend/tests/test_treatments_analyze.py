"""POST /treatments/{id}/analyze endpoint."""

import json
from datetime import date
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.api.treatments as treatments_api
from app.agents.analysis_schemas import AnalysisState
from app.db.models import AuditLogEntry, Medication, Patient, Treatment, TreatmentAnalysis
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


async def _create_treatment_for_analysis_endpoint(
    db_session: AsyncSession,
    mrn: str,
) -> UUID:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    db_session.add(patient)
    await db_session.flush()
    treatment = Treatment(
        patient_id=patient.id,
        clinical_objective="Monitor for ACE-inhibitor cough",
    )
    db_session.add(treatment)
    await db_session.flush()
    db_session.add(
        Medication(
            treatment_id=treatment.id,
            name="Lisinopril",
            dosage="10 mg",
            frequency="Once Daily (QD)",
            duration="30 days",
            objective=None,
            ordinal=0,
        )
    )
    await db_session.flush()
    return treatment.id


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_starts_analysis(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[
        tuple[task_runner.BackgroundJob, object, tuple[object, ...], dict[str, object]]
    ] = []

    def capture_schedule(
        job: task_runner.BackgroundJob,
        coro_fn: object,
        *args: object,
        **kwargs: object,
    ) -> None:
        scheduled.append((job, coro_fn, args, kwargs))

    monkeypatch.setattr(task_runner, "schedule_job", capture_schedule)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-001")

    response = await app_client.post(f"/treatments/{treatment_id}/analyze")

    assert response.status_code == 202, response.text
    analysis_id = UUID(response.json()["analysis_id"])

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.treatment_id == treatment_id
    assert analysis.status == "pending"
    assert len(scheduled) == 1
    assert scheduled[0][0].name == "analysis.run"
    assert scheduled[0][0].idempotency_key == f"analysis:{analysis_id}"
    assert scheduled[0][0].payload == {
        "analysis_id": str(analysis_id),
        "timeout_seconds": 60,
        "kb_scope_id": None,
    }
    assert scheduled[0][2][1] == analysis_id
    assert scheduled[0][2][2] == 60
    assert scheduled[0][3]["checkpoint_db_path"] == "./pharmaide.db"
    assert scheduled[0][3]["rxnorm_base_url"] == "https://rxnav.nlm.nih.gov/REST"
    assert "openai_api_key" in scheduled[0][3]
    assert scheduled[0][3]["kb_scope_id"] is None


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_passes_uuid_user_header_as_kb_scope(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[tuple[task_runner.BackgroundJob, dict[str, object]]] = []
    scope_id = uuid4()

    def capture_schedule(
        job: task_runner.BackgroundJob,
        _coro_fn: object,
        *_args: object,
        **kwargs: object,
    ) -> None:
        scheduled.append((job, kwargs))

    monkeypatch.setattr(task_runner, "schedule_job", capture_schedule)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-006")

    response = await app_client.post(
        f"/treatments/{treatment_id}/analyze",
        headers={"X-Pharmaide-User-Id": str(scope_id)},
    )

    assert response.status_code == 202, response.text
    assert scheduled[0][0].payload["kb_scope_id"] == str(scope_id)
    assert scheduled[0][1]["user_id"] == str(scope_id)
    assert scheduled[0][1]["kb_scope_id"] == scope_id


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_passes_timeout_override(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    scheduled: list[tuple[task_runner.BackgroundJob, tuple[object, ...]]] = []

    def capture_schedule(
        job: task_runner.BackgroundJob,
        _coro_fn: object,
        *args: object,
        **_kwargs: object,
    ) -> None:
        scheduled.append((job, args))

    monkeypatch.setattr(task_runner, "schedule_job", capture_schedule)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-004")

    response = await app_client.post(f"/treatments/{treatment_id}/analyze?timeout=12")

    assert response.status_code == 202, response.text
    assert len(scheduled) == 1
    assert scheduled[0][0].payload["timeout_seconds"] == 12
    assert scheduled[0][1][2] == 12


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_returns_429_when_user_is_rate_limited(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_schedule(*_args: object, **_kwargs: object) -> None:
        raise task_runner.RateLimitExceeded("pharmacist-1")

    monkeypatch.setattr(task_runner, "schedule_job", reject_schedule)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-005")

    response = await app_client.post(
        f"/treatments/{treatment_id}/analyze",
        headers={"X-Pharmaide-User-Id": "pharmacist-1"},
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert response.json() == {"detail": {"error": "analysis_rate_limited"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_background_task_starts_analysis(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_analyze(
        session_factory: async_sessionmaker[AsyncSession],
        analysis_id: UUID,
        _timeout_seconds: float,
        **_kwargs: object,
    ) -> None:
        async with session_factory() as session, session.begin():
            analysis = await session.get(TreatmentAnalysis, analysis_id)
            assert analysis is not None
            analysis.status = "running"
            analysis.started_at = func.clock_timestamp()
            session.add(
                AuditLogEntry(
                    event_type="analysis_started",
                    resource_type="treatment",
                    resource_id=analysis.treatment_id,
                    payload={
                        "treatment_id": str(analysis.treatment_id),
                        "analysis_id": str(analysis.id),
                    },
                )
            )

    monkeypatch.setattr(treatments_api, "analyze_treatment", fake_analyze)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-003")

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
async def test_post_treatment_analyze_audits_successful_run_without_phi(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_graph(*_args: object, **_kwargs: object) -> AnalysisState:
        return {
            "groundings": [],
            "ddi_warnings": [],
            "degraded": False,
            "completed_stages": ["ground_medications", "check_interactions"],
        }

    monkeypatch.setattr("app.services.analysis._run_analysis_graph", fake_graph)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-007")

    response = await app_client.post(f"/treatments/{treatment_id}/analyze")
    assert response.status_code == 202, response.text
    analysis_id = UUID(response.json()["analysis_id"])

    await task_runner.drain()

    audits = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.resource_id == treatment_id,
                AuditLogEntry.event_type.in_(("analysis_started", "analysis_completed")),
            )
            .order_by(AuditLogEntry.created_at)
        )
    ).scalars().all()
    assert [audit.event_type for audit in audits] == ["analysis_started", "analysis_completed"]
    assert all(audit.resource_type == "treatment" for audit in audits)

    started_payload = audits[0].payload
    completed_payload = audits[1].payload
    assert started_payload == {
        "treatment_id": str(treatment_id),
        "analysis_id": str(analysis_id),
        "patient_check_in_count": 0,
    }
    assert completed_payload == {
        "treatment_id": str(treatment_id),
        "analysis_id": str(analysis_id),
        "grounding_count": 0,
        "ddi_warning_count": 0,
        "kb_citation_count": 0,
        "degraded": False,
    }

    serialised_payloads = json.dumps([audit.payload for audit in audits])
    assert "Eleanor Vance" not in serialised_payloads
    assert "+18005551212" not in serialised_payloads
    assert "ANALYZE-007" not in serialised_payloads


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_rejects_duplicate_active_analysis(
    app_client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(task_runner, "schedule", lambda *_args, **_kwargs: None)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-002")

    first_response = await app_client.post(f"/treatments/{treatment_id}/analyze")
    assert first_response.status_code == 202

    second_response = await app_client.post(f"/treatments/{treatment_id}/analyze")

    assert second_response.status_code == 409
    assert second_response.json() == {"detail": {"error": "analysis_in_progress"}}


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_force_supersedes_active_analysis(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(task_runner, "schedule", lambda *_args, **_kwargs: None)

    treatment_id = await _create_treatment_for_analysis_endpoint(db_session, "ANALYZE-006")

    first_response = await app_client.post(f"/treatments/{treatment_id}/analyze")
    assert first_response.status_code == 202
    first_analysis_id = UUID(first_response.json()["analysis_id"])

    second_response = await app_client.post(f"/treatments/{treatment_id}/analyze?force=true")

    assert second_response.status_code == 202, second_response.text
    second_analysis_id = UUID(second_response.json()["analysis_id"])
    assert second_analysis_id != first_analysis_id

    first_analysis = await db_session.get(TreatmentAnalysis, first_analysis_id)
    second_analysis = await db_session.get(TreatmentAnalysis, second_analysis_id)
    assert first_analysis is not None
    assert first_analysis.status == "superseded"
    assert second_analysis is not None
    assert second_analysis.status == "pending"


@pytest.mark.usefixtures("postgres_container")
async def test_post_treatment_analyze_returns_404_for_missing_treatment(
    app_client: AsyncClient,
) -> None:
    response = await app_client.post(f"/treatments/{uuid4()}/analyze")

    assert response.status_code == 404
    assert response.json() == {"detail": {"error": "treatment_not_found"}}
