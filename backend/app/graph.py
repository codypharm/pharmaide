"""Hello-world LangGraph + SQLite checkpointer.

A throwaway counter graph whose only job is to prove the moving parts talk
to each other: FastAPI ↔ LangGraph ↔ AsyncSqliteSaver ↔ async event loop.
Real medication-flow nodes will replace this once the seams are trusted.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph


# total=False so the first invocation can pass {} without violating the
# schema. The increment node defends with .get("turn", 0) so the missing-key
# case is handled at the value layer, not the type layer.
class CounterState(TypedDict, total=False):
    turn: int


def _increment(state: CounterState) -> CounterState:
    return {"turn": state.get("turn", 0) + 1}


# Returns {} rather than the state because LangGraph state updates are merged,
# not replaced — yielding empty means "no changes from this node."
def _read(state: CounterState) -> CounterState:
    return {}


CounterGraph = CompiledStateGraph[CounterState, None, CounterState, CounterState]


def build_counter_graph(checkpointer: AsyncSqliteSaver) -> CounterGraph:
    """Two-node counter graph used as a hello-world for the LangGraph stack.

    Increments a turn counter on each invocation. Acts as a smoke test for
    the FastAPI ↔ LangGraph ↔ checkpointer ↔ async event-loop seam without
    requiring any LLM, prompt, or real state shape.
    """
    builder: StateGraph[CounterState, None, CounterState, CounterState] = StateGraph(CounterState)
    builder.add_node("increment", _increment)
    builder.add_node("read", _read)
    builder.add_edge(START, "increment")
    builder.add_edge("increment", "read")
    builder.add_edge("read", END)
    return builder.compile(checkpointer=checkpointer)


# Context manager because AsyncSqliteSaver.from_conn_string is itself an
# async context manager — it owns the SQLite connection lifecycle. Yielding
# the compiled graph keeps that ownership scoped to the caller's `async with`.
@asynccontextmanager
async def open_counter_graph(db_path: str) -> AsyncIterator[CounterGraph]:
    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        yield build_counter_graph(saver)
