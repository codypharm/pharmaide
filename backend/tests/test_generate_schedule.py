"""Analysis graph schedule generation node behavior."""

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import structlog

from app.agents.analysis_schemas import AnalysisState
from app.agents.nodes.schedule import generate_schedule
from app.logging_setup import configure_logging

FIRST_MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_MEDICATION_ID = UUID("22222222-2222-2222-2222-222222222222")
START = datetime(2026, 5, 12, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _state() -> AnalysisState:
    return {
        "medications": [
            {
                "id": FIRST_MEDICATION_ID,
                "name": "Medication One",
                "dosage": "10 mg",
                "frequency": "BID",
                "duration": "1 day",
                "objective": None,
            },
            {
                "id": SECOND_MEDICATION_ID,
                "name": "Medication Two",
                "dosage": "5 mg",
                "frequency": "Q8H",
                "duration": "1 day",
                "objective": None,
            },
        ],
        "degraded": False,
    }


def _records_with_event(captured: str, event: str) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in captured.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == event:
            records.append(record)
    return records


async def test_generate_schedule_writes_combined_deterministic_preview() -> None:
    scheduled = await generate_schedule(_state(), start_dt=START)

    assert scheduled["needs_llm_parse"] is False
    assert scheduled["schedule"] is not None
    assert [
        (slot.medication_id, slot.offset_from_start, slot.human_label)
        for slot in scheduled["schedule"].reminders
    ] == [
        (FIRST_MEDICATION_ID, timedelta(hours=0), "twice daily dose 1"),
        (SECOND_MEDICATION_ID, timedelta(hours=0), "every 8 hours dose"),
        (SECOND_MEDICATION_ID, timedelta(hours=8), "every 8 hours dose"),
        (FIRST_MEDICATION_ID, timedelta(hours=12), "twice daily dose 2"),
        (SECOND_MEDICATION_ID, timedelta(hours=16), "every 8 hours dose"),
    ]


async def test_generate_schedule_marks_llm_parse_when_medication_is_unsupported() -> None:
    state = _state()
    state["medications"][1]["frequency"] = "morning and evening with food"

    scheduled = await generate_schedule(state, start_dt=START)

    assert scheduled["needs_llm_parse"] is True
    assert scheduled["schedule"] is not None
    assert {slot.medication_id for slot in scheduled["schedule"].reminders} == {FIRST_MEDICATION_ID}


async def test_generate_schedule_returns_none_when_no_medication_can_be_scheduled() -> None:
    state = _state()
    state["medications"][0]["frequency"] = "PRN"
    state["medications"][1]["duration"] = "until finished"

    scheduled = await generate_schedule(state, start_dt=START)

    assert scheduled["needs_llm_parse"] is True
    assert scheduled["schedule"] is None


async def test_generate_schedule_logs_non_phi_summary(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("json")
    state = _state()

    await generate_schedule(state, start_dt=START)

    records = _records_with_event(capsys.readouterr().out, "schedule_generated")

    assert records
    assert records[-1]["medication_count"] == 2
    assert records[-1]["scheduled_count"] == 2
    assert records[-1]["needs_llm_parse"] is False
    assert "Medication One" not in json.dumps(records[-1])
    assert "Medication Two" not in json.dumps(records[-1])
