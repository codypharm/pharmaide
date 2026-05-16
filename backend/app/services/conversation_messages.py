"""Provider-neutral patient conversation core.

Sprint 5 messaging starts here rather than in a WhatsApp adapter. This service
stores the patient message, runs the existing safety sandwich against the
assistant draft, and stores the draft as ready or held. A later provider slice
can deliver only `draft_ready` messages.
"""

from uuid import UUID

import structlog
from pydantic import SecretStr
from pydantic_ai import Agent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.patient_reply_classifier import PatientReplyClassification
from app.agents.safety_provider_factory import ConfiguredSafetyProviders, SafetyProviderMode
from app.agents.safety_schemas import (
    GuardResult,
    PatientDraftSafetyDecision,
    RefereeResult,
    SafetyReview,
)
from app.api.schemas import (
    ConversationMessageList,
    ConversationMessageView,
    ConversationTurnView,
    TriageReason,
)
from app.db.models import AuditLogEntry, ConversationMessage, Treatment
from app.services.patient_reply_capture import (
    capture_patient_reply_state,
    triage_reason_for_patient_reply,
)
from app.services.patient_safety import review_patient_draft_safety
from app.services.triage import create_open_triage_item

log = structlog.get_logger(__name__)


class TreatmentNotFound(Exception):
    """Raised when a conversation turn references a missing treatment."""


class InvalidDeliveryRetry(Exception):
    """Raised when a message is not eligible to be queued for another send."""


async def record_patient_conversation_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: str,
    reply_classifier_agent: Agent[None, PatientReplyClassification] | None = None,
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

    await capture_patient_reply_state(
        session,
        treatment_id=treatment_id,
        inbound_message=inbound,
        classifier_agent=reply_classifier_agent,
    )
    _audit_patient_message(session, treatment_id, inbound)
    await session.flush()

    log.info(
        "patient_conversation_message_recorded",
        treatment_id=str(treatment_id),
        message_id=str(inbound.id),
        channel=inbound.channel,
    )
    return ConversationMessageView.model_validate(inbound)


async def record_pharmacist_conversation_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: str,
) -> ConversationMessageView:
    """Queue one pharmacist-authored outbound WhatsApp message."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    outbound = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="pharmacist",
        channel="whatsapp",
        status="queued",
        body=_required_text(message, "message"),
    )
    session.add(outbound)
    await session.flush()

    _audit_pharmacist_message(session, treatment_id, outbound)
    await session.flush()

    log.info(
        "pharmacist_conversation_message_queued",
        treatment_id=str(treatment_id),
        message_id=str(outbound.id),
        channel=outbound.channel,
        status=outbound.status,
    )
    return ConversationMessageView.model_validate(outbound)


async def retry_failed_conversation_message_delivery(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message_id: UUID,
) -> ConversationMessageView:
    """Move a failed outbound WhatsApp message back to the delivery queue."""
    message = await _get_treatment_message(
        session,
        treatment_id=treatment_id,
        message_id=message_id,
    )
    if message is None:
        raise TreatmentNotFound()
    if (
        message.direction != "outbound"
        or message.channel != "whatsapp"
        or message.status != "failed"
    ):
        raise InvalidDeliveryRetry()

    old_status = message.status
    message.status = "queued"
    message.external_message_id = None
    await session.flush()

    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_retried",
            resource_type="conversation_message",
            resource_id=message.id,
            # Message body is PHI-adjacent clinical text; retry audit records
            # only workflow metadata needed for accountability.
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(message.id),
                "old_status": old_status,
                "new_status": message.status,
                "channel": message.channel,
            },
        )
    )
    await session.flush()

    log.info(
        "conversation_message_delivery_retried",
        treatment_id=str(treatment_id),
        message_id=str(message.id),
        old_status=old_status,
        new_status=message.status,
        channel=message.channel,
    )
    return ConversationMessageView.model_validate(message)


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
    draft_review_reason: TriageReason | None = None,
    reply_classifier_agent: Agent[None, PatientReplyClassification] | None = None,
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
    patient_reply_classification = await capture_patient_reply_state(
        session,
        treatment_id=treatment_id,
        inbound_message=inbound,
        classifier_agent=reply_classifier_agent,
    )

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
    capture_triage_reason = triage_reason_for_patient_reply(patient_reply_classification)
    effective_draft_review_reason = draft_review_reason or capture_triage_reason
    decision = _apply_draft_review_hold(
        decision,
        draft_review_reason=effective_draft_review_reason,
    )
    triage_reason = _triage_reason_for_held_draft(decision, effective_draft_review_reason)
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
    if assistant.status == "held_for_review" and triage_reason is not None:
        await create_open_triage_item(
            session,
            treatment_id=treatment_id,
            conversation_message_id=assistant.id,
            reason=triage_reason,
        )

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


def _triage_reason_for_held_draft(
    decision: PatientDraftSafetyDecision,
    draft_review_reason: TriageReason | None,
) -> TriageReason | None:
    if decision.hold_reason == "draft_requires_review":
        return draft_review_reason
    return decision.hold_reason


def _apply_draft_review_hold(
    decision: PatientDraftSafetyDecision,
    *,
    draft_review_reason: TriageReason | None,
) -> PatientDraftSafetyDecision:
    if draft_review_reason is None or decision.status == "hold_for_pharmacist":
        return decision

    # The draft agent is allowed to be more conservative than the safety
    # sandwich. A safe-sounding reply can still need pharmacist judgement.
    return PatientDraftSafetyDecision(
        status="hold_for_pharmacist",
        review=decision.review,
        message_to_send=None,
        hold_reason="draft_requires_review",
    )


async def submit_pharmacist_takeover_holding_turn(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    patient_message: str,
    assistant_draft: str,
    reply_classifier_agent: Agent[None, PatientReplyClassification] | None = None,
) -> ConversationTurnView:
    """Record a deterministic acknowledgement while pharmacist owns the thread.

    The holding text is fixed application copy, not an LLM clinical answer. It
    stays fast so patients are not left waiting while manual review is active.
    """
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    inbound_body = _required_text(patient_message, "patient_message")
    draft_body = _required_text(assistant_draft, "assistant_draft")
    inbound = _build_patient_inbound_message(treatment_id=treatment_id, body=inbound_body)
    assistant = ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="draft_ready",
        body=draft_body,
    )
    session.add_all([inbound, assistant])
    await session.flush()
    await capture_patient_reply_state(
        session,
        treatment_id=treatment_id,
        inbound_message=inbound,
        classifier_agent=reply_classifier_agent,
    )

    decision = _allow_deterministic_holding_reply(treatment_id, draft_body)
    _audit_conversation_turn(session, treatment_id, inbound, assistant, decision.status)
    await session.flush()

    log.info(
        "pharmacist_takeover_holding_turn_recorded",
        treatment_id=str(treatment_id),
        inbound_message_id=str(inbound.id),
        assistant_message_id=str(assistant.id),
        chat_response_mode=treatment.chat_response_mode,
    )
    return ConversationTurnView(
        inbound_message=ConversationMessageView.model_validate(inbound),
        assistant_message=ConversationMessageView.model_validate(assistant),
        safety_decision=decision,
    )


async def _get_treatment_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message_id: UUID,
) -> ConversationMessage | None:
    result = await session.execute(
        select(ConversationMessage).where(
            ConversationMessage.id == message_id,
            ConversationMessage.treatment_id == treatment_id,
        )
    )
    return result.scalar_one_or_none()


def _allow_deterministic_holding_reply(
    treatment_id: UUID,
    message_to_send: str,
) -> PatientDraftSafetyDecision:
    rationale = "Deterministic holding reply while pharmacist owns the patient thread."
    review = SafetyReview(
        treatment_id=treatment_id,
        input_guard=GuardResult(
            stage="input",
            action="allow",
            categories=[],
            rationale=rationale,
            confidence=1.0,
        ),
        referee=RefereeResult(
            action="allow",
            violations=[],
            rationale=rationale,
            confidence=1.0,
        ),
        output_guard=GuardResult(
            stage="output",
            action="allow",
            categories=[],
            rationale=rationale,
            confidence=1.0,
        ),
    )
    return PatientDraftSafetyDecision(
        status="send",
        review=review,
        message_to_send=message_to_send,
        hold_reason=None,
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


def _audit_pharmacist_message(
    session: AsyncSession,
    treatment_id: UUID,
    message: ConversationMessage,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="pharmacist_conversation_message_queued",
            resource_type="conversation_message",
            resource_id=message.id,
            # Pharmacist-authored messages can include PHI and clinical advice.
            # Audit only delivery workflow metadata.
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "status": message.status,
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
