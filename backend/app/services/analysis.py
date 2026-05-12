"""Treatment analysis service.

The endpoint creates a pending row synchronously, then this background service
owns the independent database session used to advance that row through the
checkpointed medication analysis graph.
"""

import asyncio
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.analysis_graph import open_analysis_graph
from app.agents.analysis_schemas import (
    AnalysisResult,
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
)
from app.agents.nodes.summarize import build_summary_agent, build_summary_with_schedule_agent
from app.config import get_settings
from app.db.models import AuditLogEntry, Treatment, TreatmentAnalysis
from app.errors import run_graph

ConfiguredSummaryAgents = tuple[
    Agent[None, ClinicalReasoning] | None,
    Agent[None, ClinicalReasoningWithSchedule] | None,
]


class AnalysisInProgress(Exception):
    """Raised when a treatment already has an active analysis row."""


def _is_active_analysis_conflict(exc: IntegrityError) -> bool:
    return "uq_treatment_analyses_active_treatment" in str(exc)


async def create_pending_analysis(session: AsyncSession, treatment_id: UUID) -> UUID:
    """Reserve the active analysis slot before background work is scheduled.

    The endpoint returns this id immediately. The background worker later
    changes the same row to `running`, so clients can poll a stable resource.
    """
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="pending",
    )
    session.add(analysis)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_active_analysis_conflict(exc):
            raise AnalysisInProgress() from exc
        raise
    await session.refresh(analysis)
    return analysis.id


async def analyze_treatment(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    timeout_seconds: float = 60,
    *,
    checkpoint_db_path: str | None = None,
    rxnorm_base_url: str | None = None,
    openai_api_key: SecretStr | None = None,
    rxnorm_transport: httpx.AsyncBaseTransport | None = None,
    summary_agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
) -> None:
    """Run the treatment analysis graph and persist its validated result."""
    settings = get_settings()
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return
        treatment = await _get_treatment_for_analysis(session, analysis.treatment_id)
        if treatment is None:
            return

        thread_id = _ensure_thread_id(treatment)
        state = _state_from_treatment(treatment)
        analysis.status = "running"
        analysis.started_at = func.clock_timestamp()
        await session.flush()
        await session.refresh(analysis)

        audit = AuditLogEntry(
            event_type="analysis_started",
            resource_type="treatment",
            resource_id=analysis.treatment_id,
            payload={
                "treatment_id": str(analysis.treatment_id),
                "analysis_id": str(analysis.id),
            },
        )
        session.add(audit)
        await session.flush()

    try:
        final_state = await asyncio.wait_for(
            _run_analysis_graph(
                state,
                thread_id=thread_id,
                checkpoint_db_path=checkpoint_db_path or settings.checkpoint_db_path,
                rxnorm_base_url=rxnorm_base_url or settings.rxnorm_base_url,
                openai_api_key=(
                    openai_api_key if openai_api_key is not None else settings.openai_api_key
                ),
                rxnorm_transport=rxnorm_transport,
                summary_agent=summary_agent,
                schedule_agent=schedule_agent,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_timeout")
        return
    except Exception:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_failed")
        raise

    await _mark_analysis_completed(session_factory, analysis_id, final_state)


async def _get_treatment_for_analysis(
    session: AsyncSession,
    treatment_id: UUID,
) -> Treatment | None:
    result = await session.execute(
        select(Treatment)
        .where(Treatment.id == treatment_id)
        .options(selectinload(Treatment.medications))
    )
    return result.scalar_one_or_none()


def _ensure_thread_id(treatment: Treatment) -> str:
    """Materialise the stable LangGraph thread id on first analysis."""
    if treatment.langgraph_thread_id is None:
        treatment.langgraph_thread_id = f"treatment:{treatment.id}"
    return treatment.langgraph_thread_id


def _state_from_treatment(treatment: Treatment) -> AnalysisState:
    """Build the minimum medication state the graph needs, without patient PHI."""
    return {
        "treatment_id": treatment.id,
        "medications": [
            {
                "id": medication.id,
                "name": medication.name,
                "dosage": medication.dosage,
                "frequency": medication.frequency,
                "duration": medication.duration,
                "objective": medication.objective or treatment.clinical_objective,
            }
            for medication in treatment.medications
        ],
        "degraded": False,
    }


async def _run_analysis_graph(
    state: AnalysisState,
    *,
    thread_id: str,
    checkpoint_db_path: str,
    rxnorm_base_url: str,
    openai_api_key: SecretStr | None,
    rxnorm_transport: httpx.AsyncBaseTransport | None,
    summary_agent: Agent[None, ClinicalReasoning] | None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None,
) -> AnalysisState:
    """Invoke the compiled graph with shared runtime clients scoped to this run."""
    summary_agent, schedule_agent = _configured_summary_agents(
        openai_api_key,
        summary_agent=summary_agent,
        schedule_agent=schedule_agent,
    )
    async with (
        httpx.AsyncClient(
            base_url=rxnorm_base_url,
            transport=rxnorm_transport,
        ) as rxnorm_client,
        open_analysis_graph(
            checkpoint_db_path,
            rxnorm_client=rxnorm_client,
            start_dt=datetime.now(UTC),
            summary_agent=summary_agent,
            schedule_agent=schedule_agent,
        ) as graph,
    ):
        result = await run_graph(graph, thread_id=thread_id, input_state=state)
    return cast("AnalysisState", result)


def _configured_summary_agents(
    openai_api_key: SecretStr | None,
    *,
    summary_agent: Agent[None, ClinicalReasoning] | None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None,
) -> ConfiguredSummaryAgents:
    """Bridge PHARMAIDE_OPENAI_API_KEY into PydanticAI's OpenAI provider.

    Tests can inject typed agents directly. Production passes the app-prefixed
    secret from Settings so runtime does not depend on a second OPENAI_API_KEY
    environment variable being present.
    """
    if openai_api_key is None:
        return summary_agent, schedule_agent

    secret = openai_api_key.get_secret_value()
    if summary_agent is None:
        summary_agent = build_summary_agent(
            OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=secret))
        )
    if schedule_agent is None:
        schedule_agent = build_summary_with_schedule_agent(
            OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=secret))
        )
    return summary_agent, schedule_agent


async def _mark_analysis_completed(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    state: AnalysisState,
) -> None:
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return

        analysis.status = "completed"
        analysis.result = _result_from_state(state).model_dump(mode="json")
        analysis.completed_at = func.clock_timestamp()
        session.add(
            AuditLogEntry(
                event_type="analysis_completed",
                resource_type="treatment",
                resource_id=analysis.treatment_id,
                payload={
                    "treatment_id": str(analysis.treatment_id),
                    "analysis_id": str(analysis.id),
                    "grounding_count": len(state.get("groundings", [])),
                    "ddi_warning_count": len(state.get("ddi_warnings", [])),
                    "degraded": state.get("degraded", False),
                },
            )
        )


def _result_from_state(state: AnalysisState) -> AnalysisResult:
    return AnalysisResult(
        groundings=state.get("groundings", []),
        ddi_warnings=state.get("ddi_warnings", []),
        schedule=state.get("schedule"),
        reasoning=state.get("reasoning"),
        degraded=state.get("degraded", False),
    )


async def mark_analysis_failed(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    error_text: str,
) -> None:
    """Stamp a reserved analysis row failed without exposing PHI in audit data."""
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return

        analysis.status = "failed"
        analysis.error_text = error_text
        analysis.completed_at = func.clock_timestamp()
        session.add(
            AuditLogEntry(
                event_type="analysis_failed",
                resource_type="treatment",
                resource_id=analysis.treatment_id,
                payload={
                    "treatment_id": str(analysis.treatment_id),
                    "analysis_id": str(analysis.id),
                    "error": error_text,
                },
            )
        )
        await session.flush()


async def get_latest_analysis(
    session: AsyncSession, treatment_id: UUID
) -> TreatmentAnalysis | None:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(TreatmentAnalysis.treatment_id == treatment_id)
        .order_by(TreatmentAnalysis.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
