"""Placeholder delivery worker for queued WhatsApp conversation messages."""

from dataclasses import dataclass
from typing import Protocol

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, ConversationMessage

log = structlog.get_logger(__name__)

PLACEHOLDER_PROVIDER = "internal-placeholder"
DEFAULT_DELIVERY_LIMIT = 50


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
        attempt = await delivery_provider.deliver(message)
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
