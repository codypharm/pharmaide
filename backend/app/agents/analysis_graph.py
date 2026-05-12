"""LangGraph composition for Sprint 3 treatment analysis."""

from collections.abc import AsyncIterator
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
)
from app.agents.nodes.ground import ground_medications
from app.agents.nodes.interactions import check_interactions
from app.agents.nodes.schedule import generate_schedule
from app.agents.nodes.summarize import summarize_treatment

AnalysisGraph = CompiledStateGraph[AnalysisState, None, AnalysisState, AnalysisState]


def build_analysis_graph(
    checkpointer: AsyncSqliteSaver,
    *,
    rxnorm_client: httpx.AsyncClient,
    start_dt: datetime,
    summary_agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
) -> AnalysisGraph:
    """Compose the medication analysis nodes into one checkpointed graph.

    The node modules stay easy to unit-test by receiving their runtime
    dependencies as keyword-only arguments. LangGraph nodes receive only state,
    so this builder binds the shared clients/agents once at graph construction.
    """

    # RxNorm and schedule generation need runtime resources that should be
    # reused for the whole graph run, not recreated inside each node call.
    async def ground(state: AnalysisState) -> AnalysisState:
        return await ground_medications(state, rxnorm_client=rxnorm_client)

    async def schedule(state: AnalysisState) -> AnalysisState:
        return await generate_schedule(state, start_dt=start_dt)

    # Tests pass typed PydanticAI test agents here; production can omit them and
    # let summarize_treatment build the real OpenAI-backed agents lazily.
    async def summarize(state: AnalysisState) -> AnalysisState:
        return await summarize_treatment(
            state,
            agent=summary_agent,
            schedule_agent=schedule_agent,
        )

    builder: StateGraph[AnalysisState, None, AnalysisState, AnalysisState] = StateGraph(
        AnalysisState
    )
    builder.add_node("ground", ground)
    builder.add_node("interactions", check_interactions)
    builder.add_node("schedule", schedule)
    builder.add_node("summarize", summarize)
    builder.add_edge(START, "ground")
    builder.add_edge("ground", "interactions")
    builder.add_edge("interactions", "schedule")
    builder.add_edge("schedule", "summarize")
    builder.add_edge("summarize", END)
    return builder.compile(checkpointer=checkpointer)


@asynccontextmanager
async def open_analysis_graph(
    db_path: str,
    *,
    rxnorm_client: httpx.AsyncClient,
    start_dt: datetime,
    summary_agent: Agent[None, ClinicalReasoning] | None = None,
    schedule_agent: Agent[None, ClinicalReasoningWithSchedule] | None = None,
) -> AsyncIterator[AnalysisGraph]:
    """Open an analysis graph with SQLite checkpoint ownership scoped to the caller."""
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        yield build_analysis_graph(
            saver,
            rxnorm_client=rxnorm_client,
            start_dt=start_dt,
            summary_agent=summary_agent,
            schedule_agent=schedule_agent,
        )
