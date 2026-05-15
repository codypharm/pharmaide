"""Runtime validation helpers for safety provider outputs.

Safety providers are allowed to be unavailable or malformed; patient-facing
flows are not allowed to crash because of that. These helpers keep schemas
strict while converting bad provider payloads into safe blocked decisions.
"""

from collections.abc import Mapping
from typing import Any

import structlog
from pydantic import ValidationError

from app.agents.safety_schemas import (
    GuardResult,
    GuardStage,
    RefereeResult,
    RefereeViolation,
)

log = structlog.get_logger(__name__)


def validate_guard_result(stage: GuardStage, payload: Mapping[str, Any]) -> GuardResult:
    """Validate a guard payload or return a conservative blocked decision."""
    try:
        result = GuardResult.model_validate(payload)
    except ValidationError as exc:
        _log_guard_validation_failure(stage, exc)
        return _guard_fallback(stage)

    if result.stage != stage:
        log.warning(
            "safety_guard_validation_failed",
            stage=stage,
            error_count=1,
            reason="stage_mismatch",
        )
        return _guard_fallback(stage)

    return result


def validate_referee_result(payload: Mapping[str, Any]) -> RefereeResult:
    """Validate a referee payload or return a conservative blocked decision."""
    try:
        return RefereeResult.model_validate(payload)
    except ValidationError as exc:
        log.warning(
            "safety_referee_validation_failed",
            error_count=len(exc.errors()),
        )
        return RefereeResult(
            action="block",
            violations=[
                RefereeViolation(
                    violation_type="unsupported_claim",
                    description="Referee output failed validation.",
                )
            ],
            rationale="Referee output failed validation.",
            confidence=0,
            requires_pharmacist_review=True,
        )


def _guard_fallback(stage: GuardStage) -> GuardResult:
    category = "incoherent_input" if stage == "input" else "unsafe_medical_advice"
    return GuardResult(
        stage=stage,
        action="block",
        categories=[category],
        rationale="Safety guard output failed validation.",
        confidence=0,
        safe_response="I need to check this with your pharmacist before advising.",
        requires_pharmacist_review=True,
    )


def _log_guard_validation_failure(stage: GuardStage, exc: ValidationError) -> None:
    log.warning(
        "safety_guard_validation_failed",
        stage=stage,
        error_count=len(exc.errors()),
    )
