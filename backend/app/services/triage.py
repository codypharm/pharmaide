"""Triage queue service for pharmacist intervention workflows."""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import TriageItemList, TriageItemView, TriageReason
from app.db.models import AuditLogEntry, TriageItem

log = structlog.get_logger(__name__)


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
