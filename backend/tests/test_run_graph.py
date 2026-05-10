import json
from collections.abc import Mapping

import pytest
import structlog

from app.errors import run_graph
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


class _StubGraph:
    def __init__(self, *, returns: dict[str, int] | None = None, raises: Exception | None = None):
        self._returns = returns
        self._raises = raises
        self.last_config: Mapping[str, object] | None = None

    async def ainvoke(
        self,
        input_state: Mapping[str, object],
        config: Mapping[str, object] | None = None,
    ) -> object:
        self.last_config = config
        if self._raises is not None:
            raise self._raises
        assert self._returns is not None
        return self._returns


def _records_with_event(captured: str, event: str) -> list[dict[str, object]]:
    out = []
    for line in captured.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == event:
            out.append(record)
    return out


async def test_run_graph_returns_graph_result(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    graph = _StubGraph(returns={"turn": 7})

    result = await run_graph(graph, thread_id="t_alpha", input_state={"any": "input"})

    assert result == {"turn": 7}
    invoked = _records_with_event(capsys.readouterr().out, "graph_invoked")
    assert invoked, "expected a graph_invoked log line"
    assert invoked[-1]["thread_id"] == "t_alpha"


async def test_run_graph_passes_thread_id_in_config() -> None:
    graph = _StubGraph(returns={"turn": 1})

    await run_graph(graph, thread_id="t_beta", input_state={})

    assert graph.last_config == {"configurable": {"thread_id": "t_beta"}}


async def test_run_graph_logs_failure_with_thread_id_and_reraises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    graph = _StubGraph(raises=RuntimeError("graph blew up"))

    with pytest.raises(RuntimeError, match="graph blew up"):
        await run_graph(graph, thread_id="t_failing", input_state={})

    failures = _records_with_event(capsys.readouterr().out, "graph_failed")
    assert failures
    assert failures[-1]["thread_id"] == "t_failing"
    assert "RuntimeError" in str(failures[-1].get("exception", ""))
