"""Validated contracts for Sprint 4 safety guard outputs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.agents.safety_schemas import (
    GuardRequest,
    GuardResult,
    RefereeRequest,
    RefereeResult,
    RefereeViolation,
    SafetyReview,
)


def test_safety_review_composes_input_referee_and_output_decisions() -> None:
    treatment_id = uuid4()
    input_guard = GuardResult(
        stage="input",
        action="allow",
        categories=[],
        rationale="Medication adherence question.",
        confidence=0.94,
    )
    referee = RefereeResult(
        action="allow",
        violations=[],
        rationale="Draft stays within prescription and adherence guidance.",
        confidence=0.91,
    )
    output_guard = GuardResult(
        stage="output",
        action="allow",
        categories=[],
        rationale="Professional and clinically bounded.",
        confidence=0.89,
    )

    review = SafetyReview(
        treatment_id=treatment_id,
        input_guard=input_guard,
        referee=referee,
        output_guard=output_guard,
    )

    payload = review.model_dump(mode="json")

    assert payload["treatment_id"] == str(treatment_id)
    assert payload["input_guard"]["stage"] == "input"
    assert payload["referee"]["action"] == "allow"
    assert payload["output_guard"]["stage"] == "output"


def test_guard_result_requires_categories_when_not_allowed() -> None:
    with pytest.raises(ValidationError):
        GuardResult(
            stage="input",
            action="block",
            categories=[],
            rationale="Jailbreak attempt detected.",
            confidence=0.96,
        )


def test_referee_result_requires_violations_when_blocked() -> None:
    with pytest.raises(ValidationError):
        RefereeResult(
            action="block",
            violations=[],
            rationale="Draft changes the prescribed dosage.",
            confidence=0.98,
        )


def test_referee_result_accepts_blocked_dosage_change() -> None:
    result = RefereeResult(
        action="block",
        violations=[
            RefereeViolation(
                violation_type="dosage_change",
                description="Draft tells patient to double the dose.",
            )
        ],
        rationale="The assistant draft changes prescribed medication instructions.",
        confidence=0.98,
        safe_response="I need to check this with your pharmacist before advising.",
    )

    assert result.requires_pharmacist_review is True
    assert result.violations[0].violation_type == "dosage_change"


def test_guard_and_referee_requests_reject_blank_content() -> None:
    with pytest.raises(ValidationError):
        GuardRequest(
            stage="input",
            treatment_id=uuid4(),
            actor_role="patient",
            content="",
        )

    with pytest.raises(ValidationError):
        RefereeRequest(
            treatment_id=uuid4(),
            patient_message="Can I take it later?",
            assistant_draft="",
            prescription_context="Lisinopril 10 mg once daily.",
        )
