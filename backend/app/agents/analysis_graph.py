"""LangGraph composition for Sprint 3 treatment analysis."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic_ai import Agent

from app.agents.analysis_schemas import (
    AnalysisState,
    ClinicalReasoning,
    ClinicalReasoningWithSchedule,
    ClinicalSafetyReview,
)
from app.agents.nodes.clinical_safety_review import review_clinical_safety
from app.agents.nodes.ground import ground_medications
from app.agents.nodes.interactions import check_interactions
from app.agents.nodes.retrieve_kb import KnowledgeRetriever, retrieve_kb_citations
from app.agents.nodes.schedule import generate_schedule
from app.agents.nodes.summarize import summarize_treatment

AnalysisGraph = CompiledStateGraph[AnalysisState, None, AnalysisState, AnalysisState]
AnalysisNode = Callable[[AnalysisState], Awaitable[AnalysisState]]


class AnalysisGraphFailure(Exception):
    """Raised when a graph node fails after earlier nodes produced usable state."""

    def __init__(self, *, state: AnalysisState, stage: str) -> None:
        self.state = state
        self.stage = stage
        super().__init__(f"analysis graph failed during {stage}")


def build_analysis_graph(
    checkpointer: AsyncSqliteSaver,
    *,
    rxnorm_client: httpx.AsyncClient,
    start_dt: datetime,
    summary_agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
    safety_agent: Agent[None, ClinicalSafetyReview] | None = None,
    kb_retriever: KnowledgeRetriever | None = None,
) -> AnalysisGraph:
    """Compose the medication analysis nodes into one checkpointed graph.

    The node modules stay easy to unit-test by receiving their runtime
    dependencies as keyword-only arguments. LangGraph nodes receive only state,
    so this builder binds the shared clients/agents once at graph construction.
    """

    # RxNorm and schedule generation need runtime resources that should be
    # reused for the whole graph run, not recreated inside each node call.
    async def ground(state: AnalysisState) -> AnalysisState:
        return await _run_stage(
            state,
            "ground_medications",
            lambda current: ground_medications(current, rxnorm_client=rxnorm_client),
        )

    async def interactions(state: AnalysisState) -> AnalysisState:
        return await _run_stage(state, "check_interactions", check_interactions)

    async def schedule(state: AnalysisState) -> AnalysisState:
        return await _run_stage(
            state,
            "generate_schedule",
            lambda current: generate_schedule(current, start_dt=start_dt),
        )

    async def retrieve_kb(state: AnalysisState) -> AnalysisState:
        return await _run_stage(
            state,
            "retrieve_kb",
            lambda current: retrieve_kb_citations(current, retriever=kb_retriever),
        )

    async def clinical_safety_review(state: AnalysisState) -> AnalysisState:
        return await _run_stage(
            state,
            "clinical_safety_review",
            lambda current: review_clinical_safety(current, agent=safety_agent),
        )

    # Tests pass typed PydanticAI test agents here; production can omit them and
    # let summarize_treatment build the real OpenAI-backed agents lazily.
    async def summarize(state: AnalysisState) -> AnalysisState:
        return await _run_stage(
            state,
            "summarize_treatment",
            lambda current: summarize_treatment(
                current,
                agent=summary_agent,
                schedule_agent=schedule_agent,
            ),
        )

    builder: StateGraph[AnalysisState, None, AnalysisState, AnalysisState] = StateGraph(
        AnalysisState
    )
    builder.add_node("ground", ground)
    builder.add_node("interactions", interactions)
    builder.add_node("schedule", schedule)
    builder.add_node("retrieve_kb", retrieve_kb)
    builder.add_node("clinical_safety_review", clinical_safety_review)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "ground")
    builder.add_edge("ground", "interactions")
    builder.add_edge("interactions", "schedule")
    builder.add_edge("schedule", "retrieve_kb")
    builder.add_edge("retrieve_kb", "clinical_safety_review")
    builder.add_edge("clinical_safety_review", "summarize")
    builder.add_edge("summarize", END)
    return builder.compile(checkpointer=checkpointer)


async def _run_stage(
    state: AnalysisState,
    stage: str,
    node: AnalysisNode,
) -> AnalysisState:
    """Record successful stages while preserving the last usable state on failure."""
    try:
        result = await node(state)
    except AnalysisGraphFailure:
        raise
    except Exception as exc:
        raise AnalysisGraphFailure(state=state, stage=stage) from exc
    return _with_completed_stage(result, stage)


def _with_completed_stage(state: AnalysisState, stage: str) -> AnalysisState:
    """Append stage progress without mutating a node's returned state in place."""
    result = state.copy()
    completed = list(result.get("completed_stages", []))
    if stage not in completed:
        completed.append(stage)
    result["completed_stages"] = completed
    return result


@asynccontextmanager
async def open_analysis_graph(
    db_path: str,
    *,
    rxnorm_client: httpx.AsyncClient,
    start_dt: datetime,
    summary_agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
    safety_agent: Agent[None, ClinicalSafetyReview] | None = None,
    kb_retriever: KnowledgeRetriever | None = None,
) -> AsyncIterator[AnalysisGraph]:
    """Open an analysis graph with SQLite checkpoint ownership scoped to the caller."""
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        yield build_analysis_graph(
            saver,
            rxnorm_client=rxnorm_client,
            start_dt=start_dt,
            summary_agent=summary_agent,
            schedule_agent=schedule_agent,
            safety_agent=safety_agent,
            kb_retriever=kb_retriever,
        )
