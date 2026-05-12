"""Analysis graph medication grounding node behavior."""

import json
from uuid import UUID

import httpx
import pytest
import structlog

from app.agents.analysis_schemas import AnalysisState
from app.agents.nodes.ground import ground_medications
from app.logging_setup import configure_logging
from app.services.rxnorm import clear_rxnorm_cache

MEDICATION_ID = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def reset_state() -> None:
    clear_rxnorm_cache()
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def _state(name: str = "Lisinopril") -> AnalysisState:
    return {
        "medications": [
            {
                "id": MEDICATION_ID,
                "name": name,
                "dosage": "10 mg",
                "frequency": "daily",
                "duration": "30 days",
                "objective": None,
            }
        ]
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


async def test_ground_medications_adds_rxnorm_grounding() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [
                        {
                            "rxcui": "29046",
                            "name": "lisinopril",
                            "score": "85",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        grounded = await ground_medications(_state(), rxnorm_client=client)

    assert grounded["groundings"][0].medication_id == MEDICATION_ID
    assert grounded["groundings"][0].medication_name == "Lisinopril"
    assert grounded["groundings"][0].rxcui == "29046"
    assert grounded["groundings"][0].normalized_name == "lisinopril"
    assert grounded["groundings"][0].confidence == 0.85
    assert grounded["degraded"] is False


async def test_ground_medications_keeps_unmatched_medication_as_data() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"approximateGroup": {}})

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        grounded = await ground_medications(_state("Unknown Drug"), rxnorm_client=client)

    assert grounded["groundings"][0].medication_id == MEDICATION_ID
    assert grounded["groundings"][0].rxcui is None
    assert grounded["groundings"][0].normalized_name is None
    assert grounded["groundings"][0].confidence == 0
    assert grounded["degraded"] is False


async def test_ground_medications_degrades_when_rxnorm_fails_after_retries() -> None:
    attempts = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "temporarily unavailable"})

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        grounded = await ground_medications(_state("Warfarin"), rxnorm_client=client)

    assert attempts == 3
    assert grounded["groundings"][0].rxcui is None
    assert grounded["groundings"][0].confidence == 0
    assert grounded["degraded"] is True


async def test_ground_medications_uses_rxnorm_cache() -> None:
    requests = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(
            200,
            json={
                "approximateGroup": {
                    "candidate": [
                        {
                            "rxcui": "29046",
                            "name": "lisinopril",
                            "score": "100",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        await ground_medications(_state("Lisinopril"), rxnorm_client=client)
        grounded = await ground_medications(_state(" lisinopril "), rxnorm_client=client)

    assert requests == 1
    assert grounded["groundings"][0].rxcui == "29046"


async def test_ground_medications_logs_non_phi_summary(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"approximateGroup": {}})

    async with httpx.AsyncClient(
        base_url="https://rxnav.test/REST",
        transport=httpx.MockTransport(handler),
    ) as client:
        await ground_medications(_state("Patient Supplied Name"), rxnorm_client=client)

    records = _records_with_event(capsys.readouterr().out, "medications_grounded")

    assert records
    assert records[-1]["medication_count"] == 1
    assert records[-1]["matched_count"] == 0
    assert records[-1]["degraded"] is False
    assert "Patient Supplied Name" not in json.dumps(records[-1])
