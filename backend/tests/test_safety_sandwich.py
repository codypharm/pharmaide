"""Provider-neutral safety sandwich orchestration."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest
import structlog

from app.agents.safety_sandwich import can_send_to_patient, run_safety_sandwich
from app.agents.safety_schemas import GuardRequest, RefereeRequest
from app.logging_setup import configure_logging


@pytest.fixture(autouse=True)
def reset_structlog() -> None:
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


class SequencedGuardProvider:
    def __init__(self, payloads: list[Mapping[str, Any]]) -> None:
        self.payloads = payloads
        self.seen_requests: list[GuardRequest] = []

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        self.seen_requests.append(request)
        return self.payloads.pop(0)


class FakeRefereeProvider:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self.seen_requests: list[RefereeRequest] = []

    async def review(self, request: RefereeRequest) -> Mapping[str, Any]:
        self.seen_requests.append(request)
        return self.payload


async def test_safety_sandwich_allows_only_when_all_stages_allow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("json")
    treatment_id = uuid4()
    guard_provider = SequencedGuardProvider(
        [
            _guard_payload("input", "allow"),
            _guard_payload("output", "allow"),
        ]
    )
    referee_provider = FakeRefereeProvider(_referee_payload("allow"))

    review = await run_safety_sandwich(
        treatment_id=treatment_id,
        patient_message="Can I take my medicine after food?",
        assistant_draft="Please follow the timing your pharmacist approved.",
        prescription_context="Lisinopril 10 mg once daily.",
        guard_provider=guard_provider,
        referee_provider=referee_provider,
    )

    record = _last_log_record(capsys)
    assert can_send_to_patient(review) is True
    assert review.treatment_id == treatment_id
    assert review.input_guard.action == "allow"
    assert review.referee.action == "allow"
    assert review.output_guard.action == "allow"
    assert [request.stage for request in guard_provider.seen_requests] == ["input", "output"]
    assert len(referee_provider.seen_requests) == 1
    assert record["event"] == "safety_sandwich_completed"
    assert record["input_action"] == "allow"
    assert record["referee_action"] == "allow"
    assert record["output_action"] == "allow"
    assert "Can I take my medicine" not in json.dumps(record)


async def test_safety_sandwich_stops_after_blocked_input() -> None:
    treatment_id = uuid4()
    guard_provider = SequencedGuardProvider(
        [_guard_payload("input", "block", categories=["emergency"])]
    )
    referee_provider = FakeRefereeProvider(_referee_payload("allow"))

    review = await run_safety_sandwich(
        treatment_id=treatment_id,
        patient_message="I took too many pills and feel faint.",
        assistant_draft="Placeholder draft should not be checked.",
        prescription_context="Lisinopril 10 mg once daily.",
        guard_provider=guard_provider,
        referee_provider=referee_provider,
    )

    assert can_send_to_patient(review) is False
    assert review.input_guard.action == "block"
    assert review.referee.action == "block"
    assert review.output_guard.action == "block"
    assert review.referee.violations[0].violation_type == "missing_required_context"
    assert [request.stage for request in guard_provider.seen_requests] == ["input"]
    assert referee_provider.seen_requests == []


async def test_safety_sandwich_stops_after_blocked_referee() -> None:
    guard_provider = SequencedGuardProvider([_guard_payload("input", "allow")])
    referee_provider = FakeRefereeProvider(
        _referee_payload("block", violation_type="dosage_change")
    )

    review = await run_safety_sandwich(
        treatment_id=uuid4(),
        patient_message="Can I take more?",
        assistant_draft="Take two tablets tonight.",
        prescription_context="Lisinopril 10 mg once daily.",
        guard_provider=guard_provider,
        referee_provider=referee_provider,
    )

    assert can_send_to_patient(review) is False
    assert review.input_guard.action == "allow"
    assert review.referee.action == "block"
    assert review.output_guard.action == "block"
    assert review.output_guard.rationale == "Referee blocked assistant draft; output guard not run."
    assert [request.stage for request in guard_provider.seen_requests] == ["input"]
    assert len(referee_provider.seen_requests) == 1


async def test_safety_sandwich_blocks_when_output_guard_blocks() -> None:
    guard_provider = SequencedGuardProvider(
        [
            _guard_payload("input", "allow"),
            _guard_payload("output", "block", categories=["unprofessional_tone"]),
        ]
    )
    referee_provider = FakeRefereeProvider(_referee_payload("allow"))

    review = await run_safety_sandwich(
        treatment_id=uuid4(),
        patient_message="Can I take it later?",
        assistant_draft="Unsafe output tone.",
        prescription_context="Lisinopril 10 mg once daily.",
        guard_provider=guard_provider,
        referee_provider=referee_provider,
    )

    assert can_send_to_patient(review) is False
    assert review.input_guard.action == "allow"
    assert review.referee.action == "allow"
    assert review.output_guard.action == "block"
    assert [request.stage for request in guard_provider.seen_requests] == ["input", "output"]


def _guard_payload(
    stage: str,
    action: str,
    *,
    categories: list[str] | None = None,
) -> dict[str, object]:
    return {
        "stage": stage,
        "action": action,
        "categories": categories or [],
        "rationale": f"{stage} guard {action}.",
        "confidence": 0.9,
    }


def _referee_payload(
    action: str,
    *,
    violation_type: str = "unsupported_claim",
) -> dict[str, object]:
    return {
        "action": action,
        "violations": []
        if action == "allow"
        else [
            {
                "violation_type": violation_type,
                "description": "Assistant draft violates treatment context.",
            }
        ],
        "rationale": f"Referee {action}.",
        "confidence": 0.9,
    }


def _last_log_record(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    line = capsys.readouterr().out.strip().splitlines()[-1]
    return json.loads(line)
