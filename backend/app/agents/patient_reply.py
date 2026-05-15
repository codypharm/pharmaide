"""Typed patient-reply draft generation.

This agent creates a draft only; it does not send to the patient. The safety
sandwich remains the delivery gate, so this module focuses on using treatment
context and recent conversation history to produce a validated, conservative
patient-facing message.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.model_calls import run_model_with_retry

PatientReplyEscalationReason = Literal[
    "adverse_event",
    "emergency",
    "side_effect",
    "dose_change_request",
    "diagnosis_request",
    "unclear_message",
    "none",
]


class PatientReplyEnvelope(BaseModel):
    """Base class for strict patient-reply payloads."""

    model_config = ConfigDict(extra="forbid")


class MedicationContext(PatientReplyEnvelope):
    name: str = Field(min_length=1)
    dosage: str = Field(min_length=1)
    frequency: str = Field(min_length=1)
    duration: str = Field(min_length=1)
    objective: str | None = None


class ConversationMessageContext(PatientReplyEnvelope):
    direction: Literal["inbound", "outbound"]
    sender_type: Literal["patient", "assistant", "pharmacist", "system"]
    status: str = Field(min_length=1)
    body: str = Field(min_length=1)


class PatientReplyContext(PatientReplyEnvelope):
    treatment_id: UUID
    patient_message: str = Field(min_length=1)
    clinical_objective: str | None = None
    medications: list[MedicationContext] = Field(min_length=1)
    recent_messages: list[ConversationMessageContext] = Field(default_factory=list)
    latest_analysis_summary: str | None = None


class PatientReplyDraft(PatientReplyEnvelope):
    """Validated output from the patient-reply draft agent."""

    message: str = Field(min_length=1, max_length=1200)
    requires_pharmacist_review: bool
    escalation_reason: PatientReplyEscalationReason = "none"
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def require_escalation_reason_for_review(self) -> "PatientReplyDraft":
        """Held drafts need a reason the dashboard can route later."""
        if self.requires_pharmacist_review and self.escalation_reason == "none":
            raise ValueError("escalation_reason is required when pharmacist review is required")
        if not self.requires_pharmacist_review and self.escalation_reason != "none":
            raise ValueError("escalation_reason must be none when review is not required")
        return self


PATIENT_REPLY_INSTRUCTIONS = """
You are PharmaAide's patient-reply draft agent.
Return a validated patient-reply draft, not a final sent message.
Use only the treatment context, medication list, recent messages, and analysis summary provided.
Do not invent medications, diagnoses, lab values, patient facts, or clinical outcomes.
Do not change medication doses, schedules, durations, or prescriber instructions.
Do not tell the patient to start, stop, increase, decrease, or substitute medication.
For emergencies, serious adverse events, dose-change requests, diagnosis requests, unclear
messages, or side-effect reports needing clinical judgement, write a brief acknowledgement and
set requires_pharmacist_review to true with the matching escalation_reason.
Keep language clear, empathetic, and concise. Avoid medical claims that are not in the prompt.
The safety sandwich will review this draft before any delivery.
"""


def build_patient_reply_agent(
    model: Model | str = "openai:gpt-5",
) -> Agent[None, PatientReplyDraft]:
    """Build the typed PydanticAI agent used for patient-reply drafts."""
    return Agent(
        model,
        output_type=PatientReplyDraft,
        instructions=PATIENT_REPLY_INSTRUCTIONS,
        defer_model_check=True,
    )


async def draft_patient_reply(
    context: PatientReplyContext,
    *,
    agent: Agent[None, PatientReplyDraft] | None = None,
) -> PatientReplyDraft:
    """Generate a validated patient-facing draft without sending it."""
    reply_agent = agent or build_patient_reply_agent()
    result = await run_model_with_retry(
        reply_agent,
        _patient_reply_prompt(context),
        operation="draft_patient_reply",
    )
    return result.output


def _patient_reply_prompt(context: PatientReplyContext) -> str:
    return "\n".join(
        [
            "Draft a patient-facing reply for this treatment conversation.",
            f"treatment_id: {context.treatment_id}",
            f"clinical_objective: {context.clinical_objective or 'unavailable'}",
            f"patient_message: {context.patient_message}",
            "medications:",
            _medication_section(context.medications),
            "recent_messages:",
            _recent_messages_section(context.recent_messages),
            f"latest_analysis_summary: {context.latest_analysis_summary or 'unavailable'}",
        ]
    )


def _medication_section(medications: list[MedicationContext]) -> str:
    return "\n".join(
        (
            f"- name={medication.name}; dosage={medication.dosage}; "
            f"frequency={medication.frequency}; duration={medication.duration}; "
            f"objective={medication.objective or 'unavailable'}"
        )
        for medication in medications
    )


def _recent_messages_section(messages: list[ConversationMessageContext]) -> str:
    if not messages:
        return "- none"
    return "\n".join(
        (
            f"- direction={message.direction}; sender_type={message.sender_type}; "
            f"status={message.status}; body={message.body}"
        )
        for message in messages
    )
