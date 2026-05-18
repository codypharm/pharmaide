"""Placeholder delivery worker for queued WhatsApp conversation messages."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, ConversationMessage

log = structlog.get_logger(__name__)

PLACEHOLDER_PROVIDER = "internal-placeholder"
DEFAULT_DELIVERY_LIMIT = 50
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")


@dataclass(frozen=True)
class MessageDeliveryRunResult:
    processed_count: int
    sent_count: int
    failed_count: int


@dataclass(frozen=True)
class DeliveryAttemptResult:
    ok: bool
    provider: str
    external_message_id: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class DeliveryCallbackResult:
    accepted: bool
    reason: str
    message_id: UUID | None = None


class DeliveryProvider(Protocol):
    async def deliver(self, message: ConversationMessage) -> DeliveryAttemptResult:
        """Deliver one queued message through a provider-specific transport."""


class PlaceholderDeliveryProvider:
    async def deliver(self, message: ConversationMessage) -> DeliveryAttemptResult:
        """Pretend delivery succeeded until WhatsApp Business API is wired."""
        return DeliveryAttemptResult(
            ok=True,
            provider=PLACEHOLDER_PROVIDER,
            external_message_id=f"internal-delivery:{message.id}",
        )


async def run_message_delivery_once(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_DELIVERY_LIMIT,
    provider: DeliveryProvider | None = None,
) -> MessageDeliveryRunResult:
    """Move queued outbound WhatsApp messages through the delivery state machine."""
    messages = await _load_queued_whatsapp_messages(session, limit=limit)
    delivery_provider = provider or PlaceholderDeliveryProvider()
    sent_count = 0
    failed_count = 0

    for message in messages:
        old_status = message.status
        attempt = await _attempt_delivery(delivery_provider, message)
        if attempt.ok:
            _mark_message_sent(session, message, old_status=old_status, attempt=attempt)
            sent_count += 1
        else:
            _mark_message_failed(session, message, old_status=old_status, attempt=attempt)
            failed_count += 1

    await session.flush()
    log.info(
        "message_delivery_run_completed",
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=failed_count,
        provider=delivery_provider.__class__.__name__,
    )
    return MessageDeliveryRunResult(
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=failed_count,
    )


async def record_delivery_callback(
    session: AsyncSession,
    *,
    provider: str,
    external_message_id: str,
    status: str,
) -> DeliveryCallbackResult:
    """Record provider callback mismatches without trusting provider payload blindly."""
    message = await _load_message_by_external_id(session, external_message_id)
    if message is None:
        _audit_callback_rejected(
            session,
            resource_id=SYSTEM_RESOURCE_ID,
            message=None,
            provider=provider,
            external_message_id=external_message_id,
            status=status,
            reason="message_not_found",
        )
        await session.flush()
        return DeliveryCallbackResult(accepted=False, reason="message_not_found")

    if provider != PLACEHOLDER_PROVIDER:
        _audit_callback_rejected(
            session,
            resource_id=message.id,
            message=message,
            provider=provider,
            external_message_id=external_message_id,
            status=status,
            reason="provider_mismatch",
        )
        await session.flush()
        return DeliveryCallbackResult(
            accepted=False,
            reason="provider_mismatch",
            message_id=message.id,
        )

    log.info(
        "message_delivery_callback_accepted",
        message_id=str(message.id),
        provider=provider,
        callback_status=status,
    )
    return DeliveryCallbackResult(accepted=True, reason="accepted", message_id=message.id)


async def _attempt_delivery(
    provider: DeliveryProvider,
    message: ConversationMessage,
) -> DeliveryAttemptResult:
    try:
        return await provider.deliver(message)
    except Exception:
        log.exception(
            "message_delivery_provider_failed",
            message_id=str(message.id),
            treatment_id=str(message.treatment_id),
            provider=provider.__class__.__name__,
        )
        return DeliveryAttemptResult(
            ok=False,
            provider=provider.__class__.__name__,
            error_code="provider_exception",
        )


def _audit_callback_rejected(
    session: AsyncSession,
    *,
    resource_id: UUID,
    message: ConversationMessage | None,
    provider: str,
    external_message_id: str,
    status: str,
    reason: str,
) -> None:
    payload: dict[str, object] = {
        "external_message_id": external_message_id,
        "provider": provider,
        "expected_provider": PLACEHOLDER_PROVIDER,
        "callback_status": status,
        "reason": reason,
    }
    if message is not None:
        payload["message_id"] = str(message.id)

    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_callback_rejected",
            resource_type="conversation_message" if message is not None else "system",
            resource_id=resource_id,
            # Provider callbacks are untrusted. Persist only routing/state
            # metadata, never message bodies or patient identifiers.
            payload=payload,
        )
    )


def _mark_message_sent(
    session: AsyncSession,
    message: ConversationMessage,
    *,
    old_status: str,
    attempt: DeliveryAttemptResult,
) -> None:
    message.status = "sent"
    message.external_message_id = attempt.external_message_id
    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_marked_sent",
            resource_type="conversation_message",
            resource_id=message.id,
            # Message bodies may contain PHI and clinical advice. The
            # delivery audit records only routing and state metadata.
            payload={
                "treatment_id": str(message.treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "old_status": old_status,
                "new_status": message.status,
                "external_message_id": attempt.external_message_id,
                "provider": attempt.provider,
            },
        )
    )


def _mark_message_failed(
    session: AsyncSession,
    message: ConversationMessage,
    *,
    old_status: str,
    attempt: DeliveryAttemptResult,
) -> None:
    message.status = "failed"
    message.external_message_id = None
    session.add(
        AuditLogEntry(
            event_type="conversation_message_delivery_failed",
            resource_type="conversation_message",
            resource_id=message.id,
            # Failure audits must describe transport state, not message text.
            payload={
                "treatment_id": str(message.treatment_id),
                "message_id": str(message.id),
                "channel": message.channel,
                "old_status": old_status,
                "new_status": message.status,
                "provider": attempt.provider,
                "error_code": attempt.error_code or "unknown",
            },
        )
    )


async def _load_queued_whatsapp_messages(
    session: AsyncSession,
    *,
    limit: int,
) -> list[ConversationMessage]:
    result = await session.execute(
        select(ConversationMessage)
        .where(
            ConversationMessage.direction == "outbound",
            ConversationMessage.channel == "whatsapp",
            ConversationMessage.status == "queued",
        )
        .order_by(ConversationMessage.created_at.asc(), ConversationMessage.id.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def _load_message_by_external_id(
    session: AsyncSession,
    external_message_id: str,
) -> ConversationMessage | None:
    return await session.scalar(
        select(ConversationMessage).where(
            ConversationMessage.external_message_id == external_message_id,
        )
    )
