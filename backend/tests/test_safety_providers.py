"""Provider seams for Llama Guard and AgentDoG-style safety checks."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
import structlog

from app.agents.safety_providers import (
    SafetyGuardProvider,
    SafetyRefereeProvider,
    UnconfiguredGuardProvider,
    UnconfiguredRefereeProvider,
    run_guard_check,
    run_referee_check,
)
from app.agents.safety_schemas import GuardRequest, RefereeRequest
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


class FakeGuardProvider:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.seen_request: GuardRequest | None = None

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        self.seen_request = request
        return self.payload


class FakeRefereeProvider:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.seen_request: RefereeRequest | None = None

    async def review(self, request: RefereeRequest) -> Mapping[str, Any]:
        self.seen_request = request
        return self.payload


def test_fake_providers_match_runtime_protocols() -> None:
    guard: SafetyGuardProvider = FakeGuardProvider({})
    referee: SafetyRefereeProvider = FakeRefereeProvider({})

    assert guard is not None
    assert referee is not None


async def test_run_guard_check_validates_provider_payload() -> None:
    request = GuardRequest(
        stage="input",
        treatment_id=uuid4(),
        actor_role="patient",
        content="Can I take my medicine after food?",
    )
    provider = FakeGuardProvider(
        {
            "stage": "input",
            "action": "allow",
            "categories": [],
            "rationale": "Medication adherence question.",
            "confidence": 0.92,
        }
    )

    result = await run_guard_check(provider, request)

    assert provider.seen_request == request
    assert result.action == "allow"
    assert result.confidence == 0.92


async def test_unconfigured_guard_fails_closed_without_logging_message_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    request = GuardRequest(
        stage="output",
        treatment_id=uuid4(),
        actor_role="assistant",
        content="Patient-facing draft that must not appear in logs.",
    )

    result = await run_guard_check(UnconfiguredGuardProvider(), request)

    record = _last_log_record(capsys)
    assert result.action == "block"
    assert result.requires_pharmacist_review is True
    assert result.categories == ["unsafe_medical_advice"]
    assert record["event"] == "safety_guard_provider_unconfigured"
    assert record["stage"] == "output"
    assert "Patient-facing draft" not in json.dumps(record)


async def test_run_referee_check_validates_provider_payload() -> None:
    request = RefereeRequest(
        treatment_id=uuid4(),
        patient_message="Can I take it later?",
        assistant_draft="Please follow the timing your pharmacist approved.",
        prescription_context="Lisinopril 10 mg once daily.",
    )
    provider = FakeRefereeProvider(
        {
            "action": "allow",
            "violations": [],
            "rationale": "Draft stays within treatment context.",
            "confidence": 0.88,
        }
    )

    result = await run_referee_check(provider, request)

    assert provider.seen_request == request
    assert result.action == "allow"
    assert result.confidence == 0.88


async def test_unconfigured_referee_fails_closed_without_logging_draft(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    request = RefereeRequest(
        treatment_id=uuid4(),
        patient_message="I feel dizzy.",
        assistant_draft="Draft that should not be logged.",
        prescription_context="Lisinopril 10 mg once daily.",
    )

    result = await run_referee_check(UnconfiguredRefereeProvider(), request)

    record = _last_log_record(capsys)
    assert result.action == "block"
    assert result.requires_pharmacist_review is True
    assert result.violations[0].violation_type == "unsupported_claim"
    assert record["event"] == "safety_referee_provider_unconfigured"
    assert "Draft that should not be logged" not in json.dumps(record)


def _last_log_record(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    line = capsys.readouterr().out.strip().splitlines()[-1]
    return json.loads(line)
