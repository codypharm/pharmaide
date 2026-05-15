"""Provider seams for Sprint 4 safety checks.

Real Llama Guard and AgentDoG integrations should implement these protocols.
Until they are configured, the runtime helpers fail closed so patient-facing
messages are held for pharmacist review rather than sent unchecked.
"""

from collections.abc import Mapping
from typing import Any, Protocol

import structlog

from app.agents.safety_schemas import (
    GuardRequest,
    GuardResult,
    RefereeRequest,
    RefereeResult,
    RefereeViolation,
)
from app.agents.safety_validation import validate_guard_result, validate_referee_result

log = structlog.get_logger(__name__)


class SafetyGuardProvider(Protocol):
    """Adapter interface for Llama Guard-style input/output checks."""

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        """Return a raw provider payload for validation."""


class SafetyRefereeProvider(Protocol):
    """Adapter interface for AgentDoG-style prescription faithfulness checks."""

    async def review(self, request: RefereeRequest) -> Mapping[str, Any]:
        """Return a raw provider payload for validation."""


class SafetyProviderUnavailable(RuntimeError):
    """Raised when a safety provider has not been configured."""


class UnconfiguredGuardProvider:
    """Fail-closed guard provider used before Llama Guard is configured."""

    async def check(self, request: GuardRequest) -> Mapping[str, Any]:
        raise SafetyProviderUnavailable(f"{request.stage} guard provider is not configured")


class UnconfiguredRefereeProvider:
    """Fail-closed referee provider used before AgentDoG is configured."""

    async def review(self, _request: RefereeRequest) -> Mapping[str, Any]:
        raise SafetyProviderUnavailable("referee provider is not configured")


async def run_guard_check(
    provider: SafetyGuardProvider,
    request: GuardRequest,
) -> GuardResult:
    """Run and validate a guard provider, failing closed when unavailable."""
    try:
        payload = await provider.check(request)
    except SafetyProviderUnavailable:
        log.warning(
            "safety_guard_provider_unconfigured",
            stage=request.stage,
        )
        return _blocked_guard_result(request)

    return validate_guard_result(request.stage, payload)


async def run_referee_check(
    provider: SafetyRefereeProvider,
    request: RefereeRequest,
) -> RefereeResult:
    """Run and validate a referee provider, failing closed when unavailable."""
    try:
        payload = await provider.review(request)
    except SafetyProviderUnavailable:
        log.warning("safety_referee_provider_unconfigured")
        return _blocked_referee_result()

    return validate_referee_result(payload)


def _blocked_guard_result(request: GuardRequest) -> GuardResult:
    category = "incoherent_input" if request.stage == "input" else "unsafe_medical_advice"
    return GuardResult(
        stage=request.stage,
        action="block",
        categories=[category],
        rationale="Safety guard provider is not configured.",
        confidence=0,
        safe_response="I need to check this with your pharmacist before advising.",
        requires_pharmacist_review=True,
    )


def _blocked_referee_result() -> RefereeResult:
    return RefereeResult(
        action="block",
        violations=[
            RefereeViolation(
                violation_type="unsupported_claim",
                description="Referee provider is not configured.",
            )
        ],
        rationale="Referee provider is not configured.",
        confidence=0,
        requires_pharmacist_review=True,
    )
