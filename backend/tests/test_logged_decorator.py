import json

import pytest
import structlog

from app.errors import logged
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _error_records(captured: str) -> list[dict[str, object]]:
    out = []
    for line in captured.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("level") == "error":
            out.append(record)
    return out


async def test_logged_passes_through_async_return_value() -> None:
    configure_logging("json")

    @logged
    async def adder(a: int, b: int) -> int:
        return a + b

    assert await adder(2, 3) == 5


def test_logged_passes_through_sync_return_value() -> None:
    configure_logging("json")

    @logged
    def adder(a: int, b: int) -> int:
        return a + b

    assert adder(2, 3) == 5


def test_logged_reraises_sync_exceptions(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")

    @logged
    def bad() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        bad()

    errors = _error_records(capsys.readouterr().out)
    assert errors, "expected an error log record on exception"
    record = errors[-1]
    assert record["function"] == "bad"
    assert "ValueError" in str(record.get("exception", ""))


async def test_logged_reraises_async_exceptions(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")

    @logged
    async def bad_async() -> None:
        raise RuntimeError("async boom")

    with pytest.raises(RuntimeError, match="async boom"):
        await bad_async()

    errors = _error_records(capsys.readouterr().out)
    assert errors
    assert errors[-1]["function"] == "bad_async"
    assert "RuntimeError" in str(errors[-1].get("exception", ""))


def test_logged_includes_bound_contextvars(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    structlog.contextvars.bind_contextvars(request_id="req_for_failure")

    @logged
    def bad() -> None:
        raise ValueError("contextual boom")

    with pytest.raises(ValueError):
        bad()

    errors = _error_records(capsys.readouterr().out)
    assert errors[-1]["request_id"] == "req_for_failure"
