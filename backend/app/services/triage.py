"""Triage queue service for pharmacist intervention workflows."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ConversationMessageView,
    TriageApprovalView,
    TriageDeliveryView,
    TriageItemList,
    TriageItemView,
    TriageReason,
    TriageStatus,
)
from app.db.models import AuditLogEntry, ConversationMessage, Treatment, TriageItem

log = structlog.get_logger(__name__)

TRIAGE_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "open": {"acknowledged"},
    "acknowledged": {"resolved"},
    "resolved": set(),
}


class TriageItemNotFound(Exception):
    """Raised when a triage item does not exist."""


class InvalidTriageTransition(Exception):
    """Raised when a triage item status change is not allowed."""


class TriageDraftNotApprovable(Exception):
    """Raised when a triage item does not point to a held assistant draft."""


class TriageDraftNotQueueable(Exception):
    """Raised when a triage item does not point to an approved assistant draft."""


async def create_open_triage_item(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    conversation_message_id: UUID | None,
    reason: TriageReason,
) -> TriageItemView:
    """Create an open pharmacist-review item without duplicating message text."""
    item = TriageItem(
        treatment_id=treatment_id,
        conversation_message_id=conversation_message_id,
        reason=reason,
        status="open",
    )
    session.add(item)
    await session.flush()
    await _activate_pharmacist_takeover(session, treatment_id=treatment_id, triage_item=item)
    session.add(
        AuditLogEntry(
            event_type="triage_item_opened",
            resource_type="triage_item",
            resource_id=item.id,
            # Triage items point to conversation state; audit payload stays
            # metadata-only because patient messages may contain PHI.
            payload={
                "treatment_id": str(treatment_id),
                "conversation_message_id": (
                    str(conversation_message_id) if conversation_message_id else None
                ),
                "reason": reason,
                "status": "open",
            },
        )
    )
    await session.flush()
    log.info(
        "triage_item_opened",
        triage_item_id=str(item.id),
        treatment_id=str(treatment_id),
        conversation_message_id=str(conversation_message_id) if conversation_message_id else None,
        reason=reason,
        status="open",
    )
    return TriageItemView.model_validate(item)


async def _activate_pharmacist_takeover(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    triage_item: TriageItem,
) -> None:
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None or treatment.chat_response_mode == "pharmacist_takeover":
        return

    old_mode = treatment.chat_response_mode
    treatment.chat_response_mode = "pharmacist_takeover"
    session.add(
        AuditLogEntry(
            event_type="treatment_chat_response_mode_changed",
            resource_type="treatment",
            resource_id=treatment.id,
            # Conversation control changes are workflow metadata. Keep the
            # patient message and held draft body in conversation_messages only.
            payload={
                "old_chat_response_mode": old_mode,
                "new_chat_response_mode": treatment.chat_response_mode,
                "automation_mode": treatment.automation_mode,
                "trigger": "triage_item_opened",
                "triage_item_id": str(triage_item.id),
            },
        )
    )
    log.info(
        "treatment_chat_response_mode_changed",
        treatment_id=str(treatment.id),
        old_chat_response_mode=old_mode,
        new_chat_response_mode=treatment.chat_response_mode,
        automation_mode=treatment.automation_mode,
        trigger="triage_item_opened",
        triage_item_id=str(triage_item.id),
    )


async def list_triage_items(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> TriageItemList:
    """Return pharmacist triage items newest-first."""
    result = await session.execute(
        select(TriageItem)
        .order_by(TriageItem.created_at.desc(), TriageItem.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = result.scalars().all()
    log.info(
        "triage_items_listed",
        count=len(items),
        limit=limit,
        offset=offset,
    )
    return TriageItemList(items=[TriageItemView.model_validate(item) for item in items])


async def update_triage_item_status(
    session: AsyncSession,
    item_id: UUID,
    *,
    status: TriageStatus,
) -> TriageItemView:
    """Move a triage item through the pharmacist review lifecycle."""
    item = await session.get(TriageItem, item_id)
    if item is None:
        raise TriageItemNotFound()

    old_status = item.status
    if status not in TRIAGE_STATUS_TRANSITIONS.get(old_status, set()):
        raise InvalidTriageTransition()

    item.status = status
    await session.flush()
    session.add(
        AuditLogEntry(
            event_type="triage_item_status_changed",
            resource_type="triage_item",
            resource_id=item.id,
            # Status changes carry no patient text. The item itself links back
            # to the conversation message for authorized clinical review.
            payload={
                "old_status": old_status,
                "new_status": status,
            },
        )
    )
    await session.flush()
    log.info(
        "triage_item_status_changed",
        triage_item_id=str(item.id),
        old_status=old_status,
        new_status=status,
    )
    return TriageItemView.model_validate(item)


async def approve_triage_item_draft(
    session: AsyncSession,
    item_id: UUID,
) -> TriageApprovalView:
    """Approve a held assistant draft and resolve its pharmacist review item."""
    item = await session.get(TriageItem, item_id)
    if item is None:
        raise TriageItemNotFound()
    if item.status == "resolved":
        raise InvalidTriageTransition()

    message = await _get_approvable_draft(session, item)
    old_message_status = message.status
    old_triage_status = item.status

    message.status = "approved"
    item.status = "resolved"
    await session.flush()

    session.add(
        AuditLogEntry(
            event_type="triage_item_draft_approved",
            resource_type="triage_item",
            resource_id=item.id,
            # The draft body may contain PHI. Audit only state transition metadata.
            payload={
                "triage_item_id": str(item.id),
                "treatment_id": str(item.treatment_id),
                "approved_message_id": str(message.id),
                "old_message_status": old_message_status,
                "new_message_status": message.status,
                "old_triage_status": old_triage_status,
                "new_triage_status": item.status,
            },
        )
    )
    await session.flush()

    log.info(
        "triage_item_draft_approved",
        triage_item_id=str(item.id),
        treatment_id=str(item.treatment_id),
        approved_message_id=str(message.id),
        old_triage_status=old_triage_status,
        new_triage_status=item.status,
    )
    return TriageApprovalView(
        triage_item=TriageItemView.model_validate(item),
        approved_message=ConversationMessageView.model_validate(message),
    )


async def queue_triage_item_delivery(
    session: AsyncSession,
    item_id: UUID,
) -> TriageDeliveryView:
    """Mark an approved assistant draft ready for the future delivery worker."""
    item = await session.get(TriageItem, item_id)
    if item is None:
        raise TriageItemNotFound()

    message = await _get_queueable_draft(session, item)
    old_message_status = message.status

    message.status = "queued"
    await session.flush()

    session.add(
        AuditLogEntry(
            event_type="triage_item_draft_queued_for_delivery",
            resource_type="triage_item",
            resource_id=item.id,
            # Actual message delivery is provider-owned. This audit records
            # only the safe handoff state, never the patient-facing text.
            payload={
                "triage_item_id": str(item.id),
                "treatment_id": str(item.treatment_id),
                "queued_message_id": str(message.id),
                "old_message_status": old_message_status,
                "new_message_status": message.status,
                "triage_status": item.status,
            },
        )
    )
    await session.flush()

    log.info(
        "triage_item_draft_queued_for_delivery",
        triage_item_id=str(item.id),
        treatment_id=str(item.treatment_id),
        queued_message_id=str(message.id),
        old_message_status=old_message_status,
        new_message_status=message.status,
    )
    return TriageDeliveryView(
        triage_item=TriageItemView.model_validate(item),
        queued_message=ConversationMessageView.model_validate(message),
    )


async def _get_approvable_draft(
    session: AsyncSession,
    item: TriageItem,
) -> ConversationMessage:
    if item.conversation_message_id is None:
        raise TriageDraftNotApprovable()

    message = await session.get(ConversationMessage, item.conversation_message_id)
    if message is None:
        raise TriageDraftNotApprovable()

    if (
        message.treatment_id != item.treatment_id
        or message.direction != "outbound"
        or message.sender_type != "assistant"
        or message.status != "held_for_review"
    ):
        raise TriageDraftNotApprovable()

    return message


async def _get_queueable_draft(
    session: AsyncSession,
    item: TriageItem,
) -> ConversationMessage:
    if item.conversation_message_id is None:
        raise TriageDraftNotQueueable()

    message = await session.get(ConversationMessage, item.conversation_message_id)
    if message is None:
        raise TriageDraftNotQueueable()

    if (
        message.treatment_id != item.treatment_id
        or message.direction != "outbound"
        or message.sender_type != "assistant"
        or message.status != "approved"
    ):
        raise TriageDraftNotQueueable()

    return message
