"""Placeholder delivery worker for queued WhatsApp conversation messages."""

from dataclasses import dataclass

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


async def run_message_delivery_once(
    session: AsyncSession,
    *,
    limit: int = DEFAULT_DELIVERY_LIMIT,
) -> MessageDeliveryRunResult:
    """Move queued outbound WhatsApp messages to sent until a real provider lands."""
    messages = await _load_queued_whatsapp_messages(session, limit=limit)
    sent_count = 0

    for message in messages:
        old_status = message.status
        external_message_id = f"internal-delivery:{message.id}"
        message.status = "sent"
        message.external_message_id = external_message_id
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
                    "external_message_id": external_message_id,
                    "provider": PLACEHOLDER_PROVIDER,
                },
            )
        )
        sent_count += 1

    await session.flush()
    log.info(
        "message_delivery_run_completed",
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=0,
        provider=PLACEHOLDER_PROVIDER,
    )
    return MessageDeliveryRunResult(
        processed_count=len(messages),
        sent_count=sent_count,
        failed_count=0,
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
