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
    build_configured_safety_providers,
)
from app.agents.safety_sandwich import run_safety_sandwich
from app.agents.safety_schemas import SafetyReview
from app.services.safety_audit import audit_safety_review


async def review_patient_draft_safety(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    patient_message: str,
    assistant_draft: str,
    prescription_context: str,
    openai_api_key: SecretStr | None = None,
    providers: ConfiguredSafetyProviders | None = None,
) -> SafetyReview:
    """Run safety sandwich for a patient-facing draft and audit the result."""
    configured = providers or build_configured_safety_providers(openai_api_key)
    review = await run_safety_sandwich(
        treatment_id=treatment_id,
        patient_message=patient_message,
        assistant_draft=assistant_draft,
        prescription_context=prescription_context,
        guard_provider=configured.guard_provider,
        referee_provider=configured.referee_provider,
    )
    await audit_safety_review(session, review)
    return review
