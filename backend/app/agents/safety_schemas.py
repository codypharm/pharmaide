"""Validated contracts for the Sprint 4 safety sandwich.

The safety layer has three separate responsibilities: input guard, AgentDoG
referee, and output guard. These models define the data each stage may return
before any provider integration exists, so future Llama Guard or referee calls
cannot leak raw model JSON into orchestration code.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SafetyAction = Literal["allow", "block", "escalate"]
GuardStage = Literal["input", "output"]
ActorRole = Literal["patient", "assistant", "pharmacist"]
GuardCategory = Literal[
    "adverse_event",
    "emergency",
    "incoherent_input",
    "jailbreak",
    "non_medical",
    "unsafe_medical_advice",
    "unprofessional_tone",
]
RefereeViolationType = Literal[
    "diagnosis",
    "dosage_change",
    "missing_required_context",
    "prescription_mismatch",
    "unsupported_claim",
]


class SafetyEnvelope(BaseModel):
    """Base class for strict safety payloads."""

    model_config = ConfigDict(extra="forbid")


class GuardRequest(SafetyEnvelope):
    """Input or output text submitted to a guard model."""

    stage: GuardStage
    treatment_id: UUID | None = None
    actor_role: ActorRole
    content: str = Field(min_length=1)


class GuardResult(SafetyEnvelope):
    """Validated decision from an input or output guard."""

    stage: GuardStage
    action: SafetyAction
    categories: list[GuardCategory] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    safe_response: str | None = None
    requires_pharmacist_review: bool = False

    @model_validator(mode="after")
    def require_categories_for_non_allow(self) -> "GuardResult":
        """Blocked/escalated guard decisions must name the safety reason."""

        if self.action != "allow" and not self.categories:
            raise ValueError("categories are required when guard action is not allow")
        if self.action in {"block", "escalate"}:
            self.requires_pharmacist_review = True
        return self


class RefereeRequest(SafetyEnvelope):
    """Assistant draft plus prescription context submitted to AgentDoG."""

    treatment_id: UUID
    patient_message: str = Field(min_length=1)
    assistant_draft: str = Field(min_length=1)
    prescription_context: str = Field(min_length=1)


class RefereeViolation(SafetyEnvelope):
    """Specific reason the referee rejected an assistant draft."""

    violation_type: RefereeViolationType
    description: str = Field(min_length=1)


class RefereeResult(SafetyEnvelope):
    """Validated AgentDoG-style review of an assistant draft."""

    action: SafetyAction
    violations: list[RefereeViolation] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    safe_response: str | None = None
    requires_pharmacist_review: bool = False

    @model_validator(mode="after")
    def require_violations_for_non_allow(self) -> "RefereeResult":
        """Blocked/escalated referee decisions must carry concrete violations."""

        if self.action != "allow" and not self.violations:
            raise ValueError("violations are required when referee action is not allow")
        if self.action in {"block", "escalate"}:
            self.requires_pharmacist_review = True
        return self


class SafetyReview(SafetyEnvelope):
    """Combined safety sandwich decision for a patient-facing draft."""

    treatment_id: UUID
    input_guard: GuardResult
    referee: RefereeResult
    output_guard: GuardResult
