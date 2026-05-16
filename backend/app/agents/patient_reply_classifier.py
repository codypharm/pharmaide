"""Typed patient-reply intent classification.

This agent returns only structured intent state. It does not draft patient
messages, make clinical recommendations, or decide delivery. The caller uses
the validated output to update adherence/check-in state and route pharmacist
review when needed.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.models import Model

from app.agents.model_calls import run_model_with_retry

PatientReplyIntent = Literal["taken", "missed", "side_effect", "not_improving", "general"]


class PatientReplyClassifierEnvelope(BaseModel):
    """Base class for strict patient-reply classifier payloads."""

    model_config = ConfigDict(extra="forbid")


class PatientReplyClassification(PatientReplyClassifierEnvelope):
    """Validated intent before a patient reply changes monitoring state."""

    intent: PatientReplyIntent
    confidence: float = Field(ge=0, le=1)


CLASSIFIER_INSTRUCTIONS = """
Classify one patient WhatsApp message for PharmaAide monitoring state.
Return only the validated classification.
Do not draft a reply.
Do not provide clinical advice.
Use `taken` only when the patient appears to confirm a dose was taken.
Use `missed` when the patient reports forgetting, skipping, delaying, or not taking a dose.
Use `side_effect` when the patient reports symptoms that may be medication-related.
Use `not_improving` when the patient reports getting worse or not getting better.
Use `general` when the message is conversational, ambiguous, unrelated, or lacks enough evidence.
Prefer `general` over guessing.
"""


def build_patient_reply_classifier_agent(
    model: Model | str = "openai:gpt-5-nano",
) -> Agent[None, PatientReplyClassification]:
    """Build the low-latency typed classifier for patient reply intent."""
    return Agent(
        model,
        output_type=PatientReplyClassification,
        instructions=CLASSIFIER_INSTRUCTIONS,
        defer_model_check=True,
    )


async def classify_patient_reply_with_agent(
    message: str,
    *,
    agent: Agent[None, PatientReplyClassification] | None = None,
) -> PatientReplyClassification:
    """Classify a patient message with a Pydantic-validated LLM output."""
    classifier_agent = agent or build_patient_reply_classifier_agent()
    result = await run_model_with_retry(
        classifier_agent,
        "\n".join(
            [
                "Classify this patient message.",
                f"patient_message: {message}",
            ]
        ),
        operation="classify_patient_reply",
    )
    return result.output
