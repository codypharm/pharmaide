"""Retention cleanup for closed treatment lifecycle data.

Retention is deliberately archive-gated: a treatment must be closed and
explicitly archived before it can be purged. That keeps ordinary completed
treatments visible until the pharmacist or an operations process marks them as
ready for lifecycle cleanup.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, Patient, Treatment

SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")
CLOSED_TREATMENT_STATUSES = ("completed", "terminated")

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ClosedTreatmentRetentionResult:
    dry_run: bool
    retention_days: int
    eligible_treatment_count: int
    deleted_treatment_count: int
    deleted_patient_count: int
    deleted_audit_log_count: int


async def cleanup_closed_treatments(
    session: AsyncSession,
    *,
    retention_days: int,
    dry_run: bool = True,
    limit: int = 100,
    now: datetime | None = None,
) -> ClosedTreatmentRetentionResult:
    """Preview or purge archived closed treatments past the retention window."""
    cutoff = _aware_utc(now or datetime.now(UTC)) - timedelta(days=retention_days)
    treatment_rows = await _eligible_treatment_rows(session, cutoff=cutoff, limit=limit)
    treatment_ids = [row[0] for row in treatment_rows]
    patient_ids = [row[1] for row in treatment_rows]
    eligible_count = len(treatment_ids)
    orphan_patient_ids = await _orphan_patient_ids_after_treatment_delete(
        session,
        patient_ids=patient_ids,
        treatment_ids=treatment_ids,
    )

    if dry_run or not treatment_ids:
        result = ClosedTreatmentRetentionResult(
            dry_run=dry_run,
            retention_days=retention_days,
            eligible_treatment_count=eligible_count,
            deleted_treatment_count=0,
            deleted_patient_count=0,
            deleted_audit_log_count=0,
        )
        _audit_retention_cleanup(session, result)
        await session.flush()
        _log_retention_cleanup(result)
        return result

    deleted_audit_log_count = await _delete_treatment_audit_rows(session, treatment_ids)
    deleted_treatment_count = await _delete_treatments(session, treatment_ids)
    deleted_patient_count = await _delete_patients(session, orphan_patient_ids)
    result = ClosedTreatmentRetentionResult(
        dry_run=False,
        retention_days=retention_days,
        eligible_treatment_count=eligible_count,
        deleted_treatment_count=deleted_treatment_count,
        deleted_patient_count=deleted_patient_count,
        deleted_audit_log_count=deleted_audit_log_count,
    )
    _audit_retention_cleanup(session, result)
    await session.flush()
    _log_retention_cleanup(result)
    return result


async def _eligible_treatment_rows(
    session: AsyncSession,
    *,
    cutoff: datetime,
    limit: int,
) -> list[tuple[UUID, UUID]]:
    result = await session.execute(
        select(Treatment.id, Treatment.patient_id)
        .where(
            Treatment.status.in_(CLOSED_TREATMENT_STATUSES),
            Treatment.archived_at.is_not(None),
            Treatment.archived_at <= cutoff,
        )
        .order_by(Treatment.archived_at.asc(), Treatment.id.asc())
        .limit(limit)
    )
    return [(row.id, row.patient_id) for row in result]


async def _orphan_patient_ids_after_treatment_delete(
    session: AsyncSession,
    *,
    patient_ids: list[UUID],
    treatment_ids: list[UUID],
) -> list[UUID]:
    if not patient_ids:
        return []
    other_treatment_exists = (
        select(Treatment.id)
        .where(
            Treatment.patient_id == Patient.id,
            Treatment.id.not_in(treatment_ids),
        )
        .exists()
    )
    result = await session.execute(
        select(Patient.id).where(
            Patient.id.in_(patient_ids),
            ~other_treatment_exists,
        )
    )
    return list(result.scalars())


async def _count_treatment_audit_rows(
    session: AsyncSession,
    treatment_ids: list[UUID],
) -> int:
    if not treatment_ids:
        return 0
    count = await session.scalar(
        select(func.count())
        .select_from(AuditLogEntry)
        .where(
            AuditLogEntry.resource_type == "treatment",
            AuditLogEntry.resource_id.in_(treatment_ids),
        )
    )
    return int(count or 0)


async def _delete_treatment_audit_rows(
    session: AsyncSession,
    treatment_ids: list[UUID],
) -> int:
    if not treatment_ids:
        return 0
    result = await session.execute(
        delete(AuditLogEntry).where(
            AuditLogEntry.resource_type == "treatment",
            AuditLogEntry.resource_id.in_(treatment_ids),
        )
    )
    return int(result.rowcount or 0)


async def _delete_treatments(session: AsyncSession, treatment_ids: list[UUID]) -> int:
    if not treatment_ids:
        return 0
    treatments = (
        await session.execute(select(Treatment).where(Treatment.id.in_(treatment_ids)))
    ).scalars()
    deleted_count = 0
    for treatment in treatments:
        await session.delete(treatment)
        deleted_count += 1
    await session.flush()
    return deleted_count


async def _delete_patients(session: AsyncSession, patient_ids: list[UUID]) -> int:
    if not patient_ids:
        return 0
    result = await session.execute(delete(Patient).where(Patient.id.in_(patient_ids)))
    await session.flush()
    return int(result.rowcount or 0)


def _audit_retention_cleanup(
    session: AsyncSession,
    result: ClosedTreatmentRetentionResult,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="closed_treatments_retention_cleanup",
            resource_type="system",
            resource_id=SYSTEM_RESOURCE_ID,
            # Keep PHI and treatment ids out of this operational audit row.
            payload={
                "dry_run": result.dry_run,
                "retention_days": result.retention_days,
                "eligible_treatment_count": result.eligible_treatment_count,
                "deleted_treatment_count": result.deleted_treatment_count,
                "deleted_patient_count": result.deleted_patient_count,
                "deleted_audit_log_count": result.deleted_audit_log_count,
            },
        )
    )


def _log_retention_cleanup(result: ClosedTreatmentRetentionResult) -> None:
    log.info(
        "closed_treatments_retention_cleanup",
        dry_run=result.dry_run,
        retention_days=result.retention_days,
        eligible_treatment_count=result.eligible_treatment_count,
        deleted_treatment_count=result.deleted_treatment_count,
        deleted_patient_count=result.deleted_patient_count,
        deleted_audit_log_count=result.deleted_audit_log_count,
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
