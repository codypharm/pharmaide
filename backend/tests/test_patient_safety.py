"""Patient-facing draft safety review service."""

import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_provider_factory import ConfiguredSafetyProviders
from app.agents.safety_schemas import GuardRequest, RefereeRequest
from app.db.models import AuditLogEntry
from app.services.patient_safety import review_patient_draft_safety


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


async def test_review_patient_draft_safety_returns_review_and_audits(
    db_session: AsyncSession,
) -> None:
    treatment_id = uuid4()
    guard_provider = SequencedGuardProvider(
        [
            _guard_payload("input", "allow"),
            _guard_payload("output", "allow"),
        ]
    )
    referee_provider = FakeRefereeProvider(_referee_payload("allow"))

    review = await review_patient_draft_safety(
        db_session,
        treatment_id=treatment_id,
        patient_message="Can I take this after food?",
        assistant_draft="Please follow the timing your pharmacist approved.",
        prescription_context="Lisinopril 10 mg once daily.",
        providers=ConfiguredSafetyProviders(
            guard_provider=guard_provider,
            referee_provider=referee_provider,
        ),
    )
    await db_session.flush()

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "safety_review_completed")
    )

    assert review.input_guard.action == "allow"
    assert review.referee.action == "allow"
    assert review.output_guard.action == "allow"
    assert [request.stage for request in guard_provider.seen_requests] == ["input", "output"]
    assert len(referee_provider.seen_requests) == 1
    assert audit is not None
    assert audit.payload["requires_pharmacist_review"] is False
    assert "Can I take this after food" not in json.dumps(audit.payload)


async def test_review_patient_draft_safety_fails_closed_without_configured_key(
    db_session: AsyncSession,
) -> None:
    treatment_id = uuid4()

    review = await review_patient_draft_safety(
        db_session,
        treatment_id=treatment_id,
        patient_message="Can I take more medicine?",
        assistant_draft="Draft should be held because no safety provider is configured.",
        prescription_context="Lisinopril 10 mg once daily.",
        openai_api_key=None,
    )
    await db_session.flush()

    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "safety_review_completed")
    )

    assert review.input_guard.action == "block"
    assert review.referee.action == "block"
    assert review.output_guard.action == "block"
    assert audit is not None
    assert audit.payload["requires_pharmacist_review"] is True


def _guard_payload(stage: str, action: str) -> dict[str, object]:
    return {
        "stage": stage,
        "action": action,
        "categories": [],
        "rationale": f"{stage} guard {action}.",
        "confidence": 0.9,
    }


def _referee_payload(action: str) -> dict[str, object]:
    return {
        "action": action,
        "violations": [],
        "rationale": f"Referee {action}.",
        "confidence": 0.9,
    }
