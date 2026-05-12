"""Treatment analysis service.

This slice only records that analysis has started. Later Sprint 3 slices
will run the graph and stamp completed/failed outcomes onto the same row.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, TreatmentAnalysis


class AnalysisInProgress(Exception):
    """Raised when a treatment already has an active analysis row."""


def _is_active_analysis_conflict(exc: IntegrityError) -> bool:
    return "uq_treatment_analyses_active_treatment" in str(exc)


async def analyze_treatment(session: AsyncSession, treatment_id: UUID) -> UUID:
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="running",
        started_at=func.clock_timestamp(),
    )
    session.add(analysis)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_active_analysis_conflict(exc):
            raise AnalysisInProgress() from exc
        raise
    await session.refresh(analysis)

    audit = AuditLogEntry(
        event_type="analysis_started",
        resource_type="treatment",
        resource_id=treatment_id,
        payload={
            "treatment_id": str(treatment_id),
            "analysis_id": str(analysis.id),
        },
    )
    session.add(audit)
    await session.flush()

    return analysis.id
