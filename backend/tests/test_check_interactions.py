"""Analysis graph drug interaction node behavior."""

import json
from uuid import UUID

import pytest
import structlog

from app.agents.analysis_schemas import AnalysisState, MedicationGrounding
from app.agents.nodes.interactions import check_interactions
from app.logging_setup import configure_logging

FIRST_MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")
SECOND_MEDICATION_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


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


def _grounding(
    medication_id: UUID,
    *,
    rxcui: str | None,
    medication_name: str = "Medication",
) -> MedicationGrounding:
    return MedicationGrounding(
        medication_id=medication_id,
        medication_name=medication_name,
        rxcui=rxcui,
        normalized_name=medication_name.lower() if rxcui is not None else None,
        confidence=1 if rxcui is not None else 0,
    )


async def test_check_interactions_skips_when_fewer_than_two_grounded_medications() -> None:
    state: AnalysisState = {
        "groundings": [
            _grounding(FIRST_MEDICATION_ID, rxcui="29046"),
            _grounding(SECOND_MEDICATION_ID, rxcui=None),
        ],
        "degraded": False,
    }

    checked = await check_interactions(state)

    assert checked["ddi_warnings"] == []
    assert checked["degraded"] is False


async def test_check_interactions_degrades_when_provider_is_not_configured() -> None:
    state: AnalysisState = {
        "groundings": [
            _grounding(FIRST_MEDICATION_ID, rxcui="29046", medication_name="Lisinopril"),
            _grounding(SECOND_MEDICATION_ID, rxcui="11289", medication_name="Warfarin"),
        ],
        "degraded": False,
    }

    checked = await check_interactions(state)

    assert checked["ddi_warnings"] == []
    assert checked["degraded"] is True


async def test_check_interactions_logs_provider_not_configured_without_medication_names(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    state: AnalysisState = {
        "groundings": [
            _grounding(FIRST_MEDICATION_ID, rxcui="29046", medication_name="Lisinopril"),
            _grounding(SECOND_MEDICATION_ID, rxcui="11289", medication_name="Warfarin"),
        ],
        "degraded": False,
    }

    await check_interactions(state)

    records = _records_with_event(capsys.readouterr().out, "ddi_check_skipped")

    assert records
    assert records[-1]["reason"] == "provider_not_configured"
    assert records[-1]["grounded_count"] == 2
    assert records[-1]["degraded"] is True
    assert "Lisinopril" not in json.dumps(records[-1])
    assert "Warfarin" not in json.dumps(records[-1])
