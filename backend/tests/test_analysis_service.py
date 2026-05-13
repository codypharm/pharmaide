"""Treatment analysis service.

Sprint 3 starts with an inert analysis service: it creates the durable
analysis row and audit trail, but does not run the graph yet.
"""

import asyncio
from datetime import date
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from pydantic_ai.models.test import TestModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents import analysis_graph as analysis_graph_module
from app.agents.analysis_graph import AnalysisGraphFailure
from app.agents.analysis_schemas import AnalysisState, KBCitation
from app.agents.nodes.summarize import build_summary_agent
from app.db.models import AuditLogEntry, Medication, Patient, Treatment, TreatmentAnalysis
from app.services.analysis import (
    AnalysisInProgress,
    analyze_treatment,
    create_pending_analysis,
)
from app.services.rxnorm import clear_rxnorm_cache


async def _create_treatment(db_session: AsyncSession) -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn="ANALYSIS-001",
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
    return treatment


async def _add_medication(
    db_session: AsyncSession,
    treatment: Treatment,
    *,
    name: str,
    frequency: str,
    ordinal: int,
) -> Medication:
    medication = Medication(
        treatment_id=treatment.id,
        name=name,
        dosage="10 mg",
        frequency=frequency,
        duration="1 day",
        objective=treatment.clinical_objective,
        ordinal=ordinal,
    )
    db_session.add(medication)
    await db_session.flush()
    return medication


@pytest.mark.usefixtures("postgres_container")
async def test_create_pending_analysis_returns_pending_row(
    db_session: AsyncSession,
) -> None:
    treatment = await _create_treatment(db_session)

    analysis_id = await create_pending_analysis(db_session, treatment.id)

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.treatment_id == treatment.id
    assert analysis.status == "pending"
    assert analysis.started_at is None
    assert analysis.completed_at is None
    assert analysis.result is None
    assert analysis.error_text is None


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_marks_pending_row_started_and_audits(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    treatment = await _create_treatment(db_session)
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def fake_graph(*_args: object, **_kwargs: object) -> AnalysisState:
        return {"degraded": False}

    monkeypatch.setattr("app.services.analysis._run_analysis_graph", fake_graph)

    await analyze_treatment(session_factory, analysis_id)

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "completed"
    assert analysis.started_at is not None

    audit = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(
                AuditLogEntry.resource_id == treatment.id,
                AuditLogEntry.event_type == "analysis_started",
            )
        )
    ).scalar_one()
    assert audit.event_type == "analysis_started"
    assert audit.resource_type == "treatment"
    assert audit.payload == {
        "treatment_id": str(treatment.id),
        "analysis_id": str(analysis_id),
    }


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_marks_timeout_failed_and_audits(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    treatment = await _create_treatment(db_session)
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def never_finishes(*_args: object, **_kwargs: object) -> AnalysisState:
        await asyncio.sleep(1)
        return {"degraded": False}

    monkeypatch.setattr("app.services.analysis._run_analysis_graph", never_finishes)

    await analyze_treatment(session_factory, analysis_id, timeout_seconds=0.01)

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "failed"
    assert analysis.error_text == "analysis_timeout"
    assert analysis.completed_at is not None

    failed_audit = (
        await db_session.execute(
            select(AuditLogEntry).where(
                AuditLogEntry.resource_id == treatment.id,
                AuditLogEntry.event_type == "analysis_failed",
            )
        )
    ).scalar_one()
    assert failed_audit.resource_type == "treatment"
    assert failed_audit.payload == {
        "treatment_id": str(treatment.id),
        "analysis_id": str(analysis_id),
        "error": "analysis_timeout",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_runs_graph_and_persists_completed_result(
    db_session: AsyncSession,
    tmp_path: Path,
) -> None:
    treatment = await _create_treatment(db_session)
    first_medication = await _add_medication(
        db_session,
        treatment,
        name="Lisinopril",
        frequency="BID",
        ordinal=0,
    )
    await _add_medication(
        db_session,
        treatment,
        name="Warfarin",
        frequency="Q8H",
        ordinal=1,
    )
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    summary_agent = build_summary_agent(
        model=TestModel(
            custom_output_args={
                "summary": "Graph result ready for pharmacist review.",
                "red_flags": ["DDI provider is not configured."],
                "confidence": 0.81,
            }
        )
    )

    async def kb_retriever(
        _query: str,
        treatment_id: Any,
        state: AnalysisState,
    ) -> list[KBCitation]:
        assert treatment_id == treatment.id
        assert state["groundings"][0].rxcui == "29046"
        return [
            KBCitation(
                chunk_id="44444444-4444-4444-4444-444444444444",
                document_id="55555555-5555-5555-5555-555555555555",
                document_title="Anticoagulation Protocol",
                source_uri="local://kb/anticoagulation.pdf",
                text="Warfarin requires INR monitoring.",
                score=0.91,
            )
        ]

    await analyze_treatment(
        session_factory,
        analysis_id,
        checkpoint_db_path=str(tmp_path / "analysis.db"),
        rxnorm_base_url="https://rxnav.test/REST",
        rxnorm_transport=httpx.MockTransport(_rxnorm_handler),
        summary_agent=summary_agent,
        kb_retriever=kb_retriever,
    )

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "completed"
    assert analysis.completed_at is not None
    assert analysis.error_text is None
    assert analysis.result is not None
    assert analysis.result["reasoning"] == {
        "summary": "Graph result ready for pharmacist review.",
        "red_flags": ["DDI provider is not configured."],
        "confidence": 0.81,
    }
    assert analysis.result["degraded"] is True
    assert analysis.result["ddi_warnings"] == []
    assert analysis.result["kb_citations"] == [
        {
            "chunk_id": "44444444-4444-4444-4444-444444444444",
            "document_id": "55555555-5555-5555-5555-555555555555",
            "document_title": "Anticoagulation Protocol",
            "source_uri": "local://kb/anticoagulation.pdf",
            "text": "Warfarin requires INR monitoring.",
            "score": 0.91,
        }
    ]
    groundings = cast("list[dict[str, Any]]", analysis.result["groundings"])
    assert groundings[0]["medication_id"] == str(first_medication.id)
    assert groundings[0]["rxcui"] == "29046"
    assert analysis.result["schedule"] is not None

    await db_session.refresh(treatment)
    assert treatment.langgraph_thread_id == f"treatment:{treatment.id}"

    audits = (
        await db_session.execute(
            select(AuditLogEntry)
            .where(AuditLogEntry.resource_id == treatment.id)
            .order_by(AuditLogEntry.created_at)
        )
    ).scalars()
    assert [audit.event_type for audit in audits] == ["analysis_started", "analysis_completed"]


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_persists_partial_result_after_graph_failure(
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_rxnorm_cache()
    treatment = await _create_treatment(db_session)
    medication = await _add_medication(
        db_session,
        treatment,
        name="Lisinopril",
        frequency="BID",
        ordinal=0,
    )
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def failing_interactions(state: AnalysisState) -> AnalysisState:
        raise RuntimeError("ddi provider crashed")

    monkeypatch.setattr(analysis_graph_module, "check_interactions", failing_interactions)

    with pytest.raises(AnalysisGraphFailure):
        await analyze_treatment(
            session_factory,
            analysis_id,
            checkpoint_db_path=str(tmp_path / "analysis.db"),
            rxnorm_base_url="https://rxnav.test/REST",
            rxnorm_transport=httpx.MockTransport(_rxnorm_handler),
        )

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "failed"
    assert analysis.error_text == "analysis_failed"
    assert analysis.result is not None
    result = cast("dict[str, Any]", analysis.result)
    groundings = cast("list[dict[str, Any]]", result["groundings"])
    assert result["partial_results"] is True
    assert result["completed_stages"] == ["ground_medications"]
    assert groundings[0]["medication_id"] == str(medication.id)
    assert groundings[0]["rxcui"] == "29046"


@pytest.mark.usefixtures("postgres_container")
async def test_superseded_running_analysis_is_not_completed_by_old_task(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    treatment = await _create_treatment(db_session)
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    graph_started = asyncio.Event()
    release_graph = asyncio.Event()

    async def delayed_graph(*_args: object, **_kwargs: object) -> AnalysisState:
        graph_started.set()
        await release_graph.wait()
        return {"degraded": False}

    monkeypatch.setattr("app.services.analysis._run_analysis_graph", delayed_graph)
    task = asyncio.create_task(analyze_treatment(session_factory, analysis_id))
    await graph_started.wait()

    replacement_id = await create_pending_analysis(db_session, treatment.id, force=True)
    release_graph.set()
    await task

    original = await db_session.get(TreatmentAnalysis, analysis_id)
    replacement = await db_session.get(TreatmentAnalysis, replacement_id)
    assert original is not None
    assert original.status == "superseded"
    assert replacement is not None
    assert replacement.status == "pending"


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_rejects_second_active_analysis(
    db_session: AsyncSession,
) -> None:
    treatment = await _create_treatment(db_session)
    await create_pending_analysis(db_session, treatment.id)

    with pytest.raises(AnalysisInProgress):
        await create_pending_analysis(db_session, treatment.id)


async def _rxnorm_handler(request: httpx.Request) -> httpx.Response:
    term = request.url.params.get("term", "").lower()
    if "lisinopril" in term:
        return _rxnorm_response("29046", "lisinopril")
    if "warfarin" in term:
        return _rxnorm_response("11289", "warfarin")
    return httpx.Response(200, json={"approximateGroup": {}})


def _rxnorm_response(rxcui: str, name: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "approximateGroup": {
                "candidate": [
                    {
                        "rxcui": rxcui,
                        "name": name,
                        "score": "100",
                    }
                ]
            }
        },
    )
