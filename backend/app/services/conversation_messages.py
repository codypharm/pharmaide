"""Provider-neutral patient conversation core.

Sprint 5 messaging starts here rather than in a WhatsApp adapter. This service
stores the patient message, runs the existing safety sandwich against the
assistant draft, and stores the draft as ready or held. A later provider slice
can deliver only `draft_ready` messages.
"""

from uuid import UUID

import structlog
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.safety_provider_factory import ConfiguredSafetyProviders, SafetyProviderMode
from app.api.schemas import ConversationMessageList, ConversationMessageView, ConversationTurnView
from app.db.models import AuditLogEntry, ConversationMessage, Treatment
from app.services.patient_safety import review_patient_draft_safety

log = structlog.get_logger(__name__)


class TreatmentNotFound(Exception):
    """Raised when a conversation turn references a missing treatment."""


async def record_patient_conversation_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: str,
) -> ConversationMessageView:
    """Store one inbound patient message without generating a reply."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    inbound = _build_patient_inbound_message(
        treatment_id=treatment_id,
        body=_required_text(message, "message"),
    )
    session.add(inbound)
    await session.flush()

    _audit_patient_message(session, treatment_id, inbound)
    await session.flush()

    log.info(
        "patient_conversation_message_recorded",
        treatment_id=str(treatment_id),
        message_id=str(inbound.id),
        channel=inbound.channel,
    )
    return ConversationMessageView.model_validate(inbound)


async def list_conversation_messages(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    limit: int,
    offset: int,
) -> ConversationMessageList:
    """Return treatment conversation messages in chat display order."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    result = await session.execute(
        select(ConversationMessage)
        .where(ConversationMessage.treatment_id == treatment_id)
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
        .offset(offset)
    )
    messages = result.scalars().all()

    log.info(
        "conversation_messages_listed",
        treatment_id=str(treatment_id),
        count=len(messages),
        limit=limit,
        offset=offset,
    )
    return ConversationMessageList(
        items=[ConversationMessageView.model_validate(message) for message in messages]
    )


async def submit_patient_conversation_turn(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    patient_message: str,
    assistant_draft: str,
    prescription_context: str,
    openai_api_key: SecretStr | None = None,
    safety_provider: SafetyProviderMode = "model",
    llama_guard_url: str | None = None,
    agentdog_url: str | None = None,
    safety_provider_api_key: SecretStr | None = None,
    safety_provider_timeout_seconds: float = 10,
    providers: ConfiguredSafetyProviders | None = None,
) -> ConversationTurnView:
    """Record one patient turn and gate the assistant draft before delivery."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    inbound_body = _required_text(patient_message, "patient_message")
    draft_body = _required_text(assistant_draft, "assistant_draft")

    inbound = _build_patient_inbound_message(treatment_id=treatment_id, body=inbound_body)
    session.add(inbound)
    await session.flush()

    decision = await review_patient_draft_safety(
        session,
        treatment_id=treatment_id,
        patient_message=inbound_body,
        assistant_draft=draft_body,
        prescription_context=prescription_context,
        openai_api_key=openai_api_key,
        safety_provider=safety_provider,
        llama_guard_url=llama_guard_url,
        agentdog_url=agentdog_url,
        safety_provider_api_key=safety_provider_api_key,
        safety_provider_timeout_seconds=safety_provider_timeout_seconds,
        providers=providers,
    )
    assistant = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="draft_ready" if decision.status == "send" else "held_for_review",
        body=draft_body,
        safety_hold_reason=decision.hold_reason,
    )
    session.add(assistant)
    await session.flush()

    _audit_conversation_turn(session, treatment_id, inbound, assistant, decision.status)
    await session.flush()

    log.info(
        "conversation_turn_recorded",
        treatment_id=str(treatment_id),
        inbound_message_id=str(inbound.id),
        assistant_message_id=str(assistant.id),
        safety_status=decision.status,
        hold_reason=decision.hold_reason,
    )
    return ConversationTurnView(
        inbound_message=ConversationMessageView.model_validate(inbound),
        assistant_message=ConversationMessageView.model_validate(assistant),
        safety_decision=decision,
    )


def _audit_conversation_turn(
    session: AsyncSession,
    treatment_id: UUID,
    inbound: ConversationMessage,
    assistant: ConversationMessage,
    safety_status: str,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="conversation_turn_recorded",
            resource_type="conversation_message",
            resource_id=assistant.id,
            # Message bodies can contain PHI, symptoms, and medication details.
            # IDs plus safety status are enough to prove the workflow ran.
            payload={
                "treatment_id": str(treatment_id),
                "inbound_message_id": str(inbound.id),
                "assistant_message_id": str(assistant.id),
                "safety_status": safety_status,
                "hold_reason": assistant.safety_hold_reason,
            },
        )
    )


def _audit_patient_message(
    session: AsyncSession,
    treatment_id: UUID,
    message: ConversationMessage,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="patient_conversation_message_recorded",
            resource_type="conversation_message",
            resource_id=message.id,
            # Inbound message bodies can contain PHI and symptoms. Audit only
            # metadata needed to prove intake happened.
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
            },
        )
    )


def _build_patient_inbound_message(*, treatment_id: UUID, body: str) -> ConversationMessage:
    return ConversationMessage(
        treatment_id=treatment_id,
        direction="inbound",
        sender_type="patient",
        channel="whatsapp",
        status="received",
        body=body,
    )


def _required_text(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must not be blank")
    return stripped
