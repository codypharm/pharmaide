"""Service seam for patient-facing draft safety review.

Future WhatsApp and conversation routes should call this after generating an
assistant draft and before sending anything to a patient. It keeps provider
selection, sandwich execution, and non-PHI audit writing together.
"""

from uuid import UUID

from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_provider_factory import (
    ConfiguredSafetyProviders,
    SafetyProviderMode,
    build_configured_safety_providers,
)
from app.agents.safety_sandwich import can_send_to_patient, run_safety_sandwich
from app.agents.safety_schemas import (
    PatientDraftHoldReason,
    PatientDraftSafetyDecision,
    SafetyReview,
)
from app.services.safety_audit import audit_safety_review


async def review_patient_draft_safety(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    patient_message: str,
    assistant_draft: str,
    prescription_context: str,
    openai_api_key: SecretStr | None = None,
    safety_provider: SafetyProviderMode = "model",
    providers: ConfiguredSafetyProviders | None = None,
) -> PatientDraftSafetyDecision:
    """Run safety sandwich for a patient-facing draft and audit the result."""
    configured = providers or build_configured_safety_providers(
        openai_api_key,
        provider_mode=safety_provider,
    )
    review = await run_safety_sandwich(
        treatment_id=treatment_id,
        patient_message=patient_message,
        assistant_draft=assistant_draft,
        prescription_context=prescription_context,
        guard_provider=configured.guard_provider,
        referee_provider=configured.referee_provider,
    )
    await audit_safety_review(session, review)
    if can_send_to_patient(review):
        return PatientDraftSafetyDecision(
            status="send",
            review=review,
            message_to_send=assistant_draft,
            hold_reason=None,
        )
    return PatientDraftSafetyDecision(
        status="hold_for_pharmacist",
        review=review,
        message_to_send=None,
        hold_reason=_hold_reason(review),
    )


def _hold_reason(review: SafetyReview) -> PatientDraftHoldReason:
    if review.input_guard.action != "allow":
        return "input_guard"
    if review.referee.action != "allow":
        return "referee"
    return "output_guard"
