"""Provider-neutral orchestration for the patient-facing safety sandwich.

This module does not call Llama Guard or AgentDoG directly. It composes the
provider seams so future conversation routes have one safe path for deciding
whether a patient-facing draft can be sent.
"""

from uuid import UUID

import structlog

from app.agents.safety_providers import (
    SafetyGuardProvider,
    SafetyRefereeProvider,
    run_guard_check,
    run_referee_check,
)
from app.agents.safety_schemas import (
    GuardRequest,
    GuardResult,
    RefereeRequest,
    RefereeResult,
    RefereeViolation,
    SafetyReview,
)

log = structlog.get_logger(__name__)


async def run_safety_sandwich(
    *,
    treatment_id: UUID,
    patient_message: str,
    assistant_draft: str,
    prescription_context: str,
    guard_provider: SafetyGuardProvider,
    referee_provider: SafetyRefereeProvider,
) -> SafetyReview:
    """Run input guard, referee, and output guard for one assistant draft."""
    input_guard = await run_guard_check(
        guard_provider,
        GuardRequest(
            stage="input",
            treatment_id=treatment_id,
            actor_role="patient",
            content=patient_message,
        ),
    )
    if input_guard.action != "allow":
        review = SafetyReview(
            treatment_id=treatment_id,
            input_guard=input_guard,
            referee=_referee_not_run("Input guard blocked patient message; referee not run."),
            output_guard=_output_guard_not_run(
                "Input guard blocked patient message; output guard not run."
            ),
        )
        _log_safety_review(review)
        return review

    referee = await run_referee_check(
        referee_provider,
        RefereeRequest(
            treatment_id=treatment_id,
            patient_message=patient_message,
            assistant_draft=assistant_draft,
            prescription_context=prescription_context,
        ),
    )
    if referee.action != "allow":
        review = SafetyReview(
            treatment_id=treatment_id,
            input_guard=input_guard,
            referee=referee,
            output_guard=_output_guard_not_run(
                "Referee blocked assistant draft; output guard not run."
            ),
        )
        _log_safety_review(review)
        return review

    output_guard = await run_guard_check(
        guard_provider,
        GuardRequest(
            stage="output",
            treatment_id=treatment_id,
            actor_role="assistant",
            content=assistant_draft,
        ),
    )
    review = SafetyReview(
        treatment_id=treatment_id,
        input_guard=input_guard,
        referee=referee,
        output_guard=output_guard,
    )
    _log_safety_review(review)
    return review


def can_send_to_patient(review: SafetyReview) -> bool:
    """Return true only when every safety stage explicitly allowed the draft."""
    return (
        review.input_guard.action == "allow"
        and review.referee.action == "allow"
        and review.output_guard.action == "allow"
    )


def _referee_not_run(rationale: str) -> RefereeResult:
    return RefereeResult(
        action="block",
        violations=[
            RefereeViolation(
                violation_type="missing_required_context",
                description=rationale,
            )
        ],
        rationale=rationale,
        confidence=0,
        requires_pharmacist_review=True,
    )


def _output_guard_not_run(rationale: str) -> GuardResult:
    return GuardResult(
        stage="output",
        action="block",
        categories=["unsafe_medical_advice"],
        rationale=rationale,
        confidence=0,
        requires_pharmacist_review=True,
    )


def _log_safety_review(review: SafetyReview) -> None:
    log.info(
        "safety_sandwich_completed",
        input_action=review.input_guard.action,
        referee_action=review.referee.action,
        output_action=review.output_guard.action,
        requires_pharmacist_review=not can_send_to_patient(review),
    )
