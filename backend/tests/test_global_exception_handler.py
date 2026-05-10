import json

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.errors import RequestIdMiddleware, global_exception_handler
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(Exception, global_exception_handler)

    @app.get("/boom")
    async def boom() -> dict[str, str]:
        raise ValueError("kaboom")

    return app


async def test_handler_returns_sanitised_500_envelope() -> None:
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom", headers={"X-Request-ID": "req_for_500"})

    assert response.status_code == 500
    body = response.json()
    assert body == {"error": "internal_error", "request_id": "req_for_500"}


async def test_handler_does_not_leak_internals() -> None:
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    body_text = response.text
    assert "ValueError" not in body_text
    assert "kaboom" not in body_text
    assert "Traceback" not in body_text


async def test_handler_logs_exception_with_request_id_and_traceback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    transport = ASGITransport(app=_build_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/boom", headers={"X-Request-ID": "req_log_500"})

    out = capsys.readouterr().out
    error_records = [
        json.loads(line)
        for line in out.splitlines()
        if line.strip() and json.loads(line).get("event") == "unhandled_exception"
    ]
    assert error_records
    record = error_records[-1]
    assert record["level"] == "error"
    assert record["request_id"] == "req_log_500"
    assert record["path"] == "/boom"
    assert record["method"] == "GET"
    assert "ValueError" in str(record.get("exception", ""))
    assert "kaboom" in str(record.get("exception", ""))
