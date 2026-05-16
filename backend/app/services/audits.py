"""Read-only audit feed queries for pharmacist/admin dashboards."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry


async def list_audit_log_entries(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    event_type: str | None = None,
    resource_type: str | None = None,
    actor_id: UUID | None = None,
) -> list[AuditLogEntry]:
    """Return recent audit entries without joining PHI-bearing tables."""
    statement = select(AuditLogEntry)
    if event_type is not None:
        statement = statement.where(AuditLogEntry.event_type == event_type)
    if resource_type is not None:
        statement = statement.where(AuditLogEntry.resource_type == resource_type)
    if actor_id is not None:
        statement = statement.where(AuditLogEntry.actor_id == actor_id)

    result = await session.scalars(
        statement.order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)
