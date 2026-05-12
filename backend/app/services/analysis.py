"""Treatment analysis service.

The endpoint creates a pending row synchronously, then this background service
owns the independent database session used to advance that row. The graph seam
is intentionally tiny until the real LangGraph implementation lands later in
Sprint 3.
"""

import asyncio
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLogEntry, TreatmentAnalysis


class AnalysisInProgress(Exception):
    """Raised when a treatment already has an active analysis row."""


async def _run_analysis_graph() -> None:
    """Placeholder for the future LangGraph execution step.

    Timeout handling is wired before the graph exists so later slices can plug
    in real work without changing the API/task lifecycle again.
    """


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
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    timeout_seconds: float = 60,
) -> None:
    """Start the reserved analysis row and enforce a ceiling on graph work."""
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

    try:
        await asyncio.wait_for(_run_analysis_graph(), timeout=timeout_seconds)
    except TimeoutError:
        await mark_analysis_failed(session_factory, analysis_id, "analysis_timeout")


async def mark_analysis_failed(
    session_factory: async_sessionmaker[AsyncSession],
    analysis_id: UUID,
    error_text: str,
) -> None:
    """Stamp a reserved analysis row failed without exposing PHI in audit data."""
    async with session_factory() as session, session.begin():
        analysis = await session.get(TreatmentAnalysis, analysis_id)
        if analysis is None:
            return

        analysis.status = "failed"
        analysis.error_text = error_text
        analysis.completed_at = func.clock_timestamp()
        session.add(
            AuditLogEntry(
                event_type="analysis_failed",
                resource_type="treatment",
                resource_id=analysis.treatment_id,
                payload={
                    "treatment_id": str(analysis.treatment_id),
                    "analysis_id": str(analysis.id),
                    "error": error_text,
                },
            )
        )
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
