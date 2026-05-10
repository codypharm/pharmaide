import json

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.errors import RequestIdMiddleware
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    log = structlog.get_logger("test")

    @app.get("/inside")
    async def inside() -> dict[str, str]:
        log.info("inside_handler")
        return {"ok": "true"}

    return app


async def test_response_has_request_id_header() -> None:
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inside")

    assert "x-request-id" in {k.lower() for k in response.headers}
    assert response.headers["x-request-id"]


async def test_inbound_request_id_is_preserved() -> None:
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/inside", headers={"X-Request-ID": "req_caller_supplied"})

    assert response.headers["x-request-id"] == "req_caller_supplied"


async def test_request_id_appears_in_log_during_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/inside", headers={"X-Request-ID": "req_log_test"})

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "inside_handler" in ln]
    assert lines, "no log line captured for inside_handler"
    record = json.loads(lines[-1])
    assert record["request_id"] == "req_log_test"


async def test_context_cleared_after_request(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    transport = ASGITransport(app=_build_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/inside", headers={"X-Request-ID": "req_first"})

    log = structlog.get_logger("after_request")
    log.info("after_request_event")

    lines = [ln for ln in capsys.readouterr().out.splitlines() if "after_request_event" in ln]
    assert lines
    record = json.loads(lines[-1])
    assert "request_id" not in record
