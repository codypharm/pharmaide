"""Read-only audit feed queries for pharmacist/admin dashboards."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry


async def list_audit_log_entries(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> list[AuditLogEntry]:
    """Return recent audit entries without joining PHI-bearing tables."""
    result = await session.scalars(
        select(AuditLogEntry)
        .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result)
