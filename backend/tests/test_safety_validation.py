"""Provider-neutral safety validation helpers."""

import json

import pytest
import structlog

from app.agents.safety_schemas import GuardResult, RefereeResult
from app.agents.safety_validation import validate_guard_result, validate_referee_result
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_validate_guard_result_returns_valid_provider_payload() -> None:
    result = validate_guard_result(
        "input",
        {
            "stage": "input",
            "action": "allow",
            "categories": [],
            "rationale": "Medication adherence question.",
            "confidence": 0.93,
        },
    )

    assert result == GuardResult(
        stage="input",
        action="allow",
        categories=[],
        rationale="Medication adherence question.",
        confidence=0.93,
    )


def test_validate_guard_result_blocks_invalid_provider_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")

    result = validate_guard_result(
        "output",
        {
            "stage": "output",
            "action": "block",
            "categories": [],
            "rationale": "Invalid because block needs a category.",
            "confidence": 0.95,
        },
    )

    record = _last_log_record(capsys)
    assert result.action == "block"
    assert result.categories == ["unsafe_medical_advice"]
    assert result.requires_pharmacist_review is True
    assert result.confidence == 0
    assert record["event"] == "safety_guard_validation_failed"
    assert record["stage"] == "output"
    assert record["error_count"] >= 1
    assert "Invalid because block needs a category" not in json.dumps(record)


def test_validate_guard_result_blocks_stage_mismatch() -> None:
    result = validate_guard_result(
        "input",
        {
            "stage": "output",
            "action": "allow",
            "categories": [],
            "rationale": "Wrong stage.",
            "confidence": 0.9,
        },
    )

    assert result.action == "block"
    assert result.stage == "input"
    assert result.categories == ["incoherent_input"]
    assert result.requires_pharmacist_review is True


def test_validate_referee_result_blocks_invalid_provider_payload(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")

    result = validate_referee_result(
        {
            "action": "block",
            "violations": [],
            "rationale": "Invalid because block needs violations.",
            "confidence": 0.95,
        },
    )

    record = _last_log_record(capsys)
    assert result == RefereeResult(
        action="block",
        violations=[
            {
                "violation_type": "unsupported_claim",
                "description": "Referee output failed validation.",
            }
        ],
        rationale="Referee output failed validation.",
        confidence=0,
        requires_pharmacist_review=True,
    )
    assert record["event"] == "safety_referee_validation_failed"
    assert record["error_count"] >= 1
    assert "Invalid because block needs violations" not in json.dumps(record)


def test_validate_referee_result_returns_valid_provider_payload() -> None:
    result = validate_referee_result(
        {
            "action": "allow",
            "violations": [],
            "rationale": "Draft matches treatment context.",
            "confidence": 0.9,
        }
    )

    assert result.action == "allow"
    assert result.violations == []
    assert result.requires_pharmacist_review is False


def _last_log_record(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    line = capsys.readouterr().out.strip().splitlines()[-1]
    return json.loads(line)
