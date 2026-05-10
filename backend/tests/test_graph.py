from pathlib import Path
from typing import cast

from app.errors import run_graph
from app.graph import open_counter_graph


async def _invoke(db_path: str, thread_id: str) -> int:
    async with open_counter_graph(db_path) as graph:
        result = await run_graph(graph, thread_id=thread_id, input_state={})
    state = cast("dict[str, int]", result)
    return state["turn"]


async def test_first_invocation_starts_at_one(tmp_path: Path) -> None:
    db = str(tmp_path / "counter.db")
    assert await _invoke(db, "t_first") == 1


async def test_repeat_invocation_increments_within_session(tmp_path: Path) -> None:
    db = str(tmp_path / "counter.db")
    async with open_counter_graph(db) as graph:
        first = await run_graph(graph, thread_id="t1", input_state={})
        second = await run_graph(graph, thread_id="t1", input_state={})

    assert cast("dict[str, int]", first)["turn"] == 1
    assert cast("dict[str, int]", second)["turn"] == 2


async def test_threads_are_isolated(tmp_path: Path) -> None:
    db = str(tmp_path / "counter.db")
    async with open_counter_graph(db) as graph:
        await run_graph(graph, thread_id="alpha", input_state={})
        await run_graph(graph, thread_id="alpha", input_state={})
        beta_first = await run_graph(graph, thread_id="beta", input_state={})

    assert cast("dict[str, int]", beta_first)["turn"] == 1


async def test_state_persists_across_reopens(tmp_path: Path) -> None:
    """Load-bearing assertion: closing the saver and reopening from the same
    file must restore prior state. This is what proves the checkpointer is
    actually writing to disk, not just keeping state in memory."""
    db = str(tmp_path / "counter.db")

    assert await _invoke(db, "persistent") == 1
    assert await _invoke(db, "persistent") == 2
    assert await _invoke(db, "persistent") == 3
