"""Triage queue service for pharmacist intervention workflows."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import TriageItemList, TriageItemView, TriageReason, TriageStatus
from app.db.models import AuditLogEntry, TriageItem

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
