"""Treatment analysis service.

The endpoint creates a pending row synchronously, then this background service
owns the independent database session used to advance that row through the
checkpointed medication analysis graph.
"""

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import httpx
import structlog
from pydantic import SecretStr
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agents.analysis_graph import AnalysisGraphFailure, open_analysis_graph
from app.agents.analysis_schemas import (
    AnalysisResult,
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
    ClinicalSafetyReview,
    KBCitation,
    PatientCheckInState,
)
from app.agents.kb_reranker import build_reranker_agent, rerank_citations_with_agent
from app.agents.knowledge_sources.dailymed import DailyMedClient
from app.agents.nodes.clinical_safety_review import build_clinical_safety_agent
from app.agents.nodes.retrieve_kb import KnowledgeRetriever
from app.agents.nodes.summarize import build_summary_agent, build_summary_with_schedule_agent
from app.config import get_settings
from app.db.models import AuditLogEntry, PatientCheckIn, Treatment, TreatmentAnalysis
from app.errors import run_graph
from app.services.dailymed_cache import ensure_dailymed_cached_for_groundings
from app.services.embeddings import build_embedding_client, embed_texts
from app.services.kb_retrieval import Citation, retrieve

ConfiguredSummaryAgents = tuple[
    Agent[None, ClinicalReasoning] | None,
    Agent[None, ClinicalReasoningWithSchedule] | None,
    Agent[None, ClinicalSafetyReview] | None,
]
RECENT_CHECK_INS_LIMIT = 10

log = structlog.get_logger(__name__)


class AnalysisInProgress(Exception):
    """Raised when a treatment already has an active analysis row."""


def _is_active_analysis_conflict(exc: IntegrityError) -> bool:
    return "uq_treatment_analyses_active_treatment" in str(exc)


async def create_pending_analysis(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    force: bool = False,
) -> UUID:
    """Reserve the active analysis slot before background work is scheduled.

    The endpoint returns this id immediately. The background worker later
    changes the same row to `running`, so clients can poll a stable resource.
    """
    if force:
        await _supersede_active_analyses(session, treatment_id)

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


async def _supersede_active_analyses(session: AsyncSession, treatment_id: UUID) -> None:
    """Free the partial unique-index slot before creating a replacement run."""
    await session.execute(
        update(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status.in_(("pending", "running")),
        )
        .values(status="superseded", completed_at=func.clock_timestamp())
    )


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
    safety_agent: Agent[None, ClinicalSafetyReview] | None = None,
    kb_retriever: KnowledgeRetriever | None = None,
    kb_scope_id: UUID | None = None,
) -> None:
    """Run the treatment analysis graph and persist its validated result."""
    settings = get_settings()
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return
        if analysis.status == "superseded":
            return
        treatment = await _get_treatment_for_analysis(session, analysis.treatment_id)
        if treatment is None:
            return

        thread_id = _ensure_thread_id(treatment)
        check_ins = await _recent_check_ins_for_analysis(session, treatment.id)
        state = _state_from_treatment(treatment, patient_check_ins=check_ins)
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
                "patient_check_in_count": len(check_ins),
            },
        )
        session.add(audit)
        await session.flush()
        log.info(
            "analysis_context_loaded",
            treatment_id=str(treatment.id),
            analysis_id=str(analysis.id),
            medication_count=len(treatment.medications),
            patient_check_in_count=len(check_ins),
        )

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
                safety_agent=safety_agent,
                session_factory=session_factory,
                kb_retriever=kb_retriever,
                kb_scope_id=kb_scope_id,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_timeout")
        return
    except AnalysisGraphFailure as exc:
        await mark_analysis_failed(
            session_factory,
            analysis_id,
            "analysis_failed",
            partial_state=exc.state,
        )
        raise
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


async def _recent_check_ins_for_analysis(
    session: AsyncSession,
    treatment_id: UUID,
) -> list[PatientCheckIn]:
    result = await session.execute(
        select(PatientCheckIn)
        .where(PatientCheckIn.treatment_id == treatment_id)
        .order_by(PatientCheckIn.created_at.desc())
        .limit(RECENT_CHECK_INS_LIMIT)
    )
    return list(result.scalars())


def _state_from_treatment(
    treatment: Treatment,
    *,
    patient_check_ins: Sequence[PatientCheckIn],
) -> AnalysisState:
    """Build graph input without demographic identifiers.

    Patient check-in messages can contain clinical detail, so keep them in
    transient graph state rather than duplicating them into audit payloads.
    """
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
        "patient_check_ins": [
            PatientCheckInState.model_validate(check_in, from_attributes=True)
            for check_in in patient_check_ins
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
    safety_agent: Agent[None, ClinicalSafetyReview] | None,
    session_factory: async_sessionmaker[AsyncSession],
    kb_retriever: KnowledgeRetriever | None,
    kb_scope_id: UUID | None,
) -> AnalysisState:
    """Invoke the compiled graph with shared runtime clients scoped to this run."""
    summary_agent, schedule_agent, safety_agent = _configured_summary_agents(
        openai_api_key,
        summary_agent=summary_agent,
        schedule_agent=schedule_agent,
        safety_agent=safety_agent,
    )
    configured_kb_retriever = _configured_kb_retriever(
        session_factory,
        openai_api_key,
        kb_retriever=kb_retriever,
        kb_scope_id=kb_scope_id,
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
            safety_agent=safety_agent,
            kb_retriever=configured_kb_retriever,
        ) as graph,
    ):
        result = await run_graph(graph, thread_id=thread_id, input_state=state)
    return cast("AnalysisState", result)


def _configured_summary_agents(
    openai_api_key: SecretStr | None,
    *,
    summary_agent: Agent[None, ClinicalReasoning] | None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None,
    safety_agent: Agent[None, ClinicalSafetyReview] | None,
) -> ConfiguredSummaryAgents:
    """Bridge PHARMAIDE_OPENAI_API_KEY into PydanticAI's OpenAI provider.

    Tests can inject typed agents directly. Production passes the app-prefixed
    secret from Settings so runtime does not depend on a second OPENAI_API_KEY
    environment variable being present.
    """
    if openai_api_key is None:
        return summary_agent, schedule_agent, safety_agent

    secret = openai_api_key.get_secret_value()
    if summary_agent is None:
        summary_agent = build_summary_agent(
            OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=secret))
        )
    if schedule_agent is None:
        schedule_agent = build_summary_with_schedule_agent(
            OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=secret))
        )
    if safety_agent is None:
        safety_agent = build_clinical_safety_agent(
            OpenAIResponsesModel("gpt-5", provider=OpenAIProvider(api_key=secret))
        )
    return summary_agent, schedule_agent, safety_agent


def _configured_kb_retriever(
    session_factory: async_sessionmaker[AsyncSession],
    openai_api_key: SecretStr | None,
    *,
    kb_retriever: KnowledgeRetriever | None,
    kb_scope_id: UUID | None,
) -> KnowledgeRetriever | None:
    if kb_retriever is not None:
        return kb_retriever
    if openai_api_key is None or kb_scope_id is None:
        return None

    secret = openai_api_key.get_secret_value()
    reranker_agent = build_reranker_agent(
        OpenAIResponsesModel("gpt-5-mini", provider=OpenAIProvider(api_key=secret))
    )

    async def configured_retriever(
        query: str,
        treatment_id: UUID | None,
        state: AnalysisState,
    ) -> list[KBCitation]:
        embedding_client = build_embedding_client(openai_api_key)

        async def embedder(texts: Sequence[str]) -> list[list[float]]:
            return await embed_texts(texts, client=embedding_client)

        async def reranker(
            rerank_query: str,
            candidates: Sequence[Citation],
            limit: int,
        ):
            return await rerank_citations_with_agent(
                rerank_query,
                candidates,
                limit,
                agent=reranker_agent,
            )

        try:
            async with (
                httpx.AsyncClient() as dailymed_http_client,
                session_factory() as session,
                session.begin(),
            ):
                await ensure_dailymed_cached_for_groundings(
                    session,
                    groundings=state.get("groundings", []),
                    client=DailyMedClient(http_client=dailymed_http_client),
                    embedder=embedder,
                )
                citations = await retrieve(
                    session,
                    query,
                    embedder=embedder,
                    reranker=reranker,
                    k=5,
                    candidate_k=20,
                    treatment_id=treatment_id,
                    uploaded_by=kb_scope_id,
                )
        finally:
            await embedding_client.close()

        return [_kb_citation_from_retrieval(citation) for citation in citations]

    return configured_retriever


def _kb_citation_from_retrieval(citation: Citation) -> KBCitation:
    return KBCitation(
        chunk_id=citation.chunk_id,
        document_id=citation.document_id,
        source_type=citation.source_type,
        document_title=citation.document_title,
        source_uri=citation.source_uri,
        text=citation.text,
        score=citation.score,
    )


async def _mark_analysis_completed(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    state: AnalysisState,
) -> None:
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return
        if analysis.status == "superseded":
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
                    "kb_citation_count": len(state.get("kb_citations", [])),
                    "degraded": state.get("degraded", False),
                },
            )
        )


def _result_from_state(
    state: AnalysisState,
    *,
    partial_results: bool = False,
) -> AnalysisResult:
    return AnalysisResult(
        groundings=state.get("groundings", []),
        ddi_warnings=state.get("ddi_warnings", []),
        schedule=state.get("schedule"),
        kb_citations=state.get("kb_citations", []),
        clinical_safety_review=state.get("clinical_safety_review"),
        reasoning=state.get("reasoning"),
        degraded=state.get("degraded", False),
        partial_results=partial_results,
        completed_stages=state.get("completed_stages", []),
    )


async def mark_analysis_failed(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    error_text: str,
    *,
    partial_state: AnalysisState | None = None,
) -> None:
    """Stamp a reserved analysis row failed without exposing PHI in audit data."""
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return
        if analysis.status == "superseded":
            return

        analysis.status = "failed"
        analysis.error_text = error_text
        if partial_state is not None:
            analysis.result = _result_from_state(
                partial_state,
                partial_results=True,
            ).model_dump(mode="json")
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


async def get_latest_completed_analysis(
    session: AsyncSession, treatment_id: UUID
) -> TreatmentAnalysis | None:
    """Return the newest completed analysis with a durable result, if any."""
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status == "completed",
            TreatmentAnalysis.result.is_not(None),
        )
        .order_by(TreatmentAnalysis.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
