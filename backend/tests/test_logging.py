import json

import pytest
import structlog

from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_console_mode_emits_event_and_keys(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("console")
    log = structlog.get_logger("test")

    log.info("dose_recorded", patient_id="p_1", turn=2)

    out = capsys.readouterr().out
    assert "dose_recorded" in out
    assert "patient_id" in out
    assert "p_1" in out


def test_json_mode_emits_parseable_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    log = structlog.get_logger("test")

    log.info("dose_recorded", patient_id="p_1", turn=2)

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["event"] == "dose_recorded"
    assert record["patient_id"] == "p_1"
    assert record["turn"] == 2
    assert record["level"] == "info"
    assert "timestamp" in record


def test_contextvars_are_merged_into_log_records(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    structlog.contextvars.bind_contextvars(request_id="req_123")
    log = structlog.get_logger("test")

    log.info("event_in_request")

    line = capsys.readouterr().out.strip().splitlines()[-1]
    record = json.loads(line)

    assert record["request_id"] == "req_123"
