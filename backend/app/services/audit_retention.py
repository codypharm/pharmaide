"""Retention cleanup for low-risk operational audit rows.

Clinical and pharmacist-decision audit logs are evidence, so this cleanup is
deliberately limited to system-operation noise that can be regenerated from
infrastructure logs if needed.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry

SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")
OPERATIONAL_AUDIT_EVENT_TYPES = (
    "checkpoints_cleaned",
    "closed_treatments_retention_cleanup",
    "dailymed_cache_cleaned",
    "kb_removed_upload_files_cleaned",
    "operational_audit_retention_cleanup",
    "queue_dead_letter_received",
    "queue_task_retry_observed",
)

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class OperationalAuditRetentionResult:
    dry_run: bool
    retention_days: int
    eligible_audit_log_count: int
    deleted_audit_log_count: int


async def cleanup_operational_audit_logs(
    session: AsyncSession,
    *,
    retention_days: int,
    dry_run: bool = True,
    limit: int = 1000,
    now: datetime | None = None,
) -> OperationalAuditRetentionResult:
    """Preview or purge old operational audit rows only."""
    cutoff = _aware_utc(now or datetime.now(UTC)) - timedelta(days=retention_days)
    audit_ids = await _eligible_operational_audit_ids(session, cutoff=cutoff, limit=limit)
    eligible_count = len(audit_ids)

    if dry_run or not audit_ids:
        result = OperationalAuditRetentionResult(
            dry_run=dry_run,
            retention_days=retention_days,
            eligible_audit_log_count=eligible_count,
            deleted_audit_log_count=0,
        )
        _audit_retention_cleanup(session, result)
        await session.flush()
        _log_retention_cleanup(result)
        return result

    deleted_count = await _delete_audit_rows(session, audit_ids)
    result = OperationalAuditRetentionResult(
        dry_run=False,
        retention_days=retention_days,
        eligible_audit_log_count=eligible_count,
        deleted_audit_log_count=deleted_count,
    )
    _audit_retention_cleanup(session, result)
    await session.flush()
    _log_retention_cleanup(result)
    return result


async def _eligible_operational_audit_ids(
    session: AsyncSession,
    *,
    cutoff: datetime,
    limit: int,
) -> list[UUID]:
    result = await session.execute(
        select(AuditLogEntry.id)
        .where(
            AuditLogEntry.event_type.in_(OPERATIONAL_AUDIT_EVENT_TYPES),
            AuditLogEntry.created_at <= cutoff,
        )
        .order_by(AuditLogEntry.created_at.asc(), AuditLogEntry.id.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def _delete_audit_rows(session: AsyncSession, audit_ids: list[UUID]) -> int:
    result = await session.execute(delete(AuditLogEntry).where(AuditLogEntry.id.in_(audit_ids)))
    return int(result.rowcount or 0)


def _audit_retention_cleanup(
    session: AsyncSession,
    result: OperationalAuditRetentionResult,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="operational_audit_retention_cleanup",
            resource_type="system",
            resource_id=SYSTEM_RESOURCE_ID,
            # Counts only. Never copy deleted event payloads into the cleanup row.
            payload={
                "dry_run": result.dry_run,
                "retention_days": result.retention_days,
                "eligible_audit_log_count": result.eligible_audit_log_count,
                "deleted_audit_log_count": result.deleted_audit_log_count,
            },
        )
    )


def _log_retention_cleanup(result: OperationalAuditRetentionResult) -> None:
    log.info(
        "operational_audit_retention_cleanup",
        dry_run=result.dry_run,
        retention_days=result.retention_days,
        eligible_audit_log_count=result.eligible_audit_log_count,
        deleted_audit_log_count=result.deleted_audit_log_count,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
