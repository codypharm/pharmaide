"""Treatment course completion detection.

Completion is deliberately tied to queued reminder audit markers, not just the
clock. That prevents a worker from marking a course completed before the final
scheduled reminders have actually been queued for delivery.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.analysis_schemas import AnalysisResult
from app.db.models import AuditLogEntry, Treatment, TreatmentAnalysis
from app.services.schedule_keys import reminder_key_for_slot

log = structlog.get_logger(__name__)

CompletionReason = Literal[
    "completed",
    "treatment_not_active",
    "no_schedule",
    "future_reminders",
    "unqueued_reminders",
]


class TreatmentNotFound(Exception):
    """Raised when course completion is requested for a missing treatment."""


@dataclass(frozen=True)
class CourseCompletionResult:
    completed: bool
    reason: CompletionReason


async def complete_treatment_course_if_finished(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    now: datetime | None = None,
) -> CourseCompletionResult:
    """Mark an active treatment completed once every scheduled reminder is queued."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.status != "active":
        return CourseCompletionResult(completed=False, reason="treatment_not_active")

    analysis = await _latest_completed_analysis_with_result(session, treatment_id)
    if analysis is None:
        return CourseCompletionResult(completed=False, reason="no_schedule")
    analysis_result = _validated_analysis_result(analysis)
    if analysis_result is None or analysis_result.schedule is None:
        return CourseCompletionResult(completed=False, reason="no_schedule")

    reminders = analysis_result.schedule.reminders
    if not reminders:
        return CourseCompletionResult(completed=False, reason="no_schedule")

    anchor = treatment.treatment_start_at or treatment.created_at
    current_time = _aware_utc(now or datetime.now(UTC))
    has_future_reminder = any(
        _aware_utc(anchor) + reminder.offset_from_start > current_time
        for reminder in reminders
    )
    if has_future_reminder:
        return CourseCompletionResult(completed=False, reason="future_reminders")

    reminder_keys = [reminder_key_for_slot(reminder) for reminder in reminders]
    if not await _all_reminders_have_been_queued(
        session,
        treatment_id=treatment_id,
        reminder_keys=reminder_keys,
    ):
        return CourseCompletionResult(completed=False, reason="unqueued_reminders")

    old_status = treatment.status
    treatment.status = "completed"
    _audit_treatment_completed(
        session,
        treatment=treatment,
        old_status=old_status,
        analysis_id=analysis.id,
        scheduled_reminder_count=len(reminders),
    )
    await session.flush()
    log.info(
        "treatment_completed",
        treatment_id=str(treatment_id),
        analysis_id=str(analysis.id),
        scheduled_reminder_count=len(reminders),
    )
    return CourseCompletionResult(completed=True, reason="completed")


async def _latest_completed_analysis_with_result(
    session: AsyncSession,
    treatment_id: UUID,
) -> TreatmentAnalysis | None:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status == "completed",
            TreatmentAnalysis.result.is_not(None),
        )
        .order_by(TreatmentAnalysis.created_at.desc(), TreatmentAnalysis.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _validated_analysis_result(analysis: TreatmentAnalysis) -> AnalysisResult | None:
    try:
        return AnalysisResult.model_validate(analysis.result)
    except ValidationError:
        log.warning(
            "course_completion_analysis_result_invalid",
            treatment_id=str(analysis.treatment_id),
            analysis_id=str(analysis.id),
        )
        return None


async def _all_reminders_have_been_queued(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    reminder_keys: list[str],
) -> bool:
    queued_keys: set[str] = set()
    result = await session.execute(
        select(AuditLogEntry.payload).where(
            AuditLogEntry.event_type == "monitoring_message_queued",
            AuditLogEntry.payload.contains({"treatment_id": str(treatment_id)}),
        )
    )
    for payload in result.scalars():
        reminder_key = payload.get("reminder_key")
        if isinstance(reminder_key, str):
            queued_keys.add(reminder_key)
    return set(reminder_keys).issubset(queued_keys)


def _audit_treatment_completed(
    session: AsyncSession,
    *,
    treatment: Treatment,
    old_status: str,
    analysis_id: UUID,
    scheduled_reminder_count: int,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="treatment_completed",
            resource_type="treatment",
            resource_id=treatment.id,
            # Store only workflow metadata. Medication names and patient
            # messages stay in their clinical tables, not in audit payloads.
            payload={
                "old_status": old_status,
                "new_status": treatment.status,
                "analysis_id": str(analysis_id),
                "scheduled_reminder_count": scheduled_reminder_count,
            },
        )
    )


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
