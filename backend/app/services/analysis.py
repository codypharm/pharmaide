"""Treatment analysis service.

This slice only records that analysis has started. Later Sprint 3 slices
will run the graph and stamp completed/failed outcomes onto the same row.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLogEntry, TreatmentAnalysis


class AnalysisInProgress(Exception):
    """Raised when a treatment already has an active analysis row."""


def _is_active_analysis_conflict(exc: IntegrityError) -> bool:
    return "uq_treatment_analyses_active_treatment" in str(exc)


async def create_pending_analysis(session: AsyncSession, treatment_id: UUID) -> UUID:
    """Reserve the active analysis slot before background work is scheduled.

    The endpoint returns this id immediately. The background worker later
    changes the same row to `running`, so clients can poll a stable resource.
    """
    analysis = TreatmentAnalysis(
        treatment_id=treatment_id,
        status="pending",
    )
    session.add(analysis)
    try:
        await session.flush()
    except IntegrityError as exc:
        if _is_active_analysis_conflict(exc):
            raise AnalysisInProgress() from exc
        raise
    await session.refresh(analysis)
    return analysis.id


async def analyze_treatment(
    session_factory: async_sessionmaker[AsyncSession], analysis_id: UUID
) -> None:
    """Start the reserved analysis row in an independent background session."""
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return

        analysis.status = "running"
        analysis.started_at = func.clock_timestamp()
        await session.flush()
        await session.refresh(analysis)

        audit = AuditLogEntry(
            event_type="analysis_started",
            resource_type="treatment",
            resource_id=analysis.treatment_id,
            payload={
                "treatment_id": str(analysis.treatment_id),
                "analysis_id": str(analysis.id),
            },
        )
        session.add(audit)
        await session.flush()


async def get_latest_analysis(
    session: AsyncSession, treatment_id: UUID
) -> TreatmentAnalysis | None:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(TreatmentAnalysis.treatment_id == treatment_id)
        .order_by(TreatmentAnalysis.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
