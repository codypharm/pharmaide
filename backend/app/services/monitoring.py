"""Turn active treatment schedules into queued patient messages.

This is the internal worker seam that will later be called by Cloud Tasks or
Pub/Sub. It deliberately creates provider-neutral conversation rows first;
WhatsApp delivery remains the separate message-delivery worker.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.analysis_schemas import AnalysisResult, ReminderSlot
from app.db.models import (
    AuditLogEntry,
    ConversationMessage,
    Medication,
    Treatment,
    TreatmentAnalysis,
)

log = structlog.get_logger(__name__)
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")


class TreatmentNotFound(Exception):
    """Raised when an internal monitoring run references a missing treatment."""


class TreatmentNotActive(Exception):
    """Raised when monitoring is requested before Start Cycle activates it."""


@dataclass(frozen=True)
class MonitoringRunResult:
    queued_count: int
    skipped_count: int


@dataclass(frozen=True)
class DueMonitoringRunResult:
    processed_count: int
    queued_count: int
    skipped_count: int


async def run_due_monitoring(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    limit: int = 100,
) -> DueMonitoringRunResult:
    """Run due monitoring across active treatments ready for automation."""
    treatment_ids = await _load_active_automated_treatment_ids(session, limit=limit)
    queued_count = 0
    skipped_count = 0

    for treatment_id in treatment_ids:
        result = await run_due_monitoring_for_treatment(
            session,
            treatment_id=treatment_id,
            now=now,
        )
        queued_count += result.queued_count
        skipped_count += result.skipped_count

    _audit_due_monitoring_run(
        session,
        processed_count=len(treatment_ids),
        queued_count=queued_count,
        skipped_count=skipped_count,
        limit=limit,
    )
    await session.flush()
    log.info(
        "due_monitoring_run_completed",
        processed_count=len(treatment_ids),
        queued_count=queued_count,
        skipped_count=skipped_count,
        limit=limit,
    )
    return DueMonitoringRunResult(
        processed_count=len(treatment_ids),
        queued_count=queued_count,
        skipped_count=skipped_count,
    )


async def run_due_monitoring_for_treatment(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    now: datetime | None = None,
) -> MonitoringRunResult:
    """Queue due reminder messages for one active treatment schedule."""
    treatment = await _load_active_treatment(session, treatment_id)
    analysis_result = await _load_latest_analysis_result(session, treatment_id)
    if analysis_result.schedule is None:
        return MonitoringRunResult(queued_count=0, skipped_count=0)

    anchor = treatment.treatment_start_at or treatment.created_at
    current_time = _aware_utc(now or datetime.now(UTC))
    medications = {medication.id: medication for medication in treatment.medications}
    queued_count = 0
    skipped_count = 0

    for reminder in analysis_result.schedule.reminders:
        medication = medications.get(reminder.medication_id)
        if medication is None:
            skipped_count += 1
            continue

        scheduled_for = _aware_utc(anchor) + reminder.offset_from_start
        if scheduled_for > current_time:
            skipped_count += 1
            continue

        reminder_key = reminder_key_for_slot(reminder)
        if await _reminder_already_queued(session, treatment_id, reminder_key):
            skipped_count += 1
            continue

        message = _build_reminder_message(
            treatment_id=treatment_id,
            medication=medication,
            human_label=reminder.human_label,
        )
        session.add(message)
        await session.flush()
        _audit_monitoring_message(
            session,
            treatment_id=treatment_id,
            message=message,
            reminder_key=reminder_key,
            scheduled_for=scheduled_for,
        )
        queued_count += 1

    await session.flush()
    log.info(
        "treatment_due_monitoring_run",
        treatment_id=str(treatment_id),
        queued_count=queued_count,
        skipped_count=skipped_count,
    )
    return MonitoringRunResult(queued_count=queued_count, skipped_count=skipped_count)


async def _load_active_automated_treatment_ids(
    session: AsyncSession,
    *,
    limit: int,
) -> list[UUID]:
    result = await session.execute(
        select(Treatment.id)
        .where(
            Treatment.status == "active",
            Treatment.automation_mode == "active",
        )
        .order_by(Treatment.treatment_start_at.asc().nullslast(), Treatment.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars())


async def _load_active_treatment(session: AsyncSession, treatment_id: UUID) -> Treatment:
    result = await session.execute(
        select(Treatment)
        .where(Treatment.id == treatment_id)
        .options(selectinload(Treatment.medications))
    )
    treatment = result.scalar_one_or_none()
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.status != "active":
        raise TreatmentNotActive()
    return treatment


async def _load_latest_analysis_result(
    session: AsyncSession,
    treatment_id: UUID,
) -> AnalysisResult:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status == "completed",
        )
        .order_by(TreatmentAnalysis.created_at.desc(), TreatmentAnalysis.id.desc())
    )
    for analysis in result.scalars():
        if analysis.result is None:
            continue
        try:
            return AnalysisResult.model_validate(analysis.result)
        except ValidationError:
            log.warning(
                "monitoring_analysis_result_invalid",
                treatment_id=str(treatment_id),
                analysis_id=str(analysis.id),
            )
            continue
    return AnalysisResult(
        groundings=[],
        ddi_warnings=[],
        schedule=None,
        reasoning=None,
        degraded=True,
        completed_stages=[],
    )


def _build_reminder_message(
    *,
    treatment_id: UUID,
    medication: Medication,
    human_label: str,
) -> ConversationMessage:
    return ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body=(
            f"Reminder: it is time for {medication.name} ({human_label}). "
            "Reply when taken, or tell us if you are having trouble with this dose."
        ),
    )


def _audit_monitoring_message(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    message: ConversationMessage,
    reminder_key: str,
    scheduled_for: datetime,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="monitoring_message_queued",
            resource_type="conversation_message",
            resource_id=message.id,
            # Reminder message bodies include medication text, so the audit
            # marker stores only workflow metadata and a deterministic slot key.
            payload={
                "treatment_id": str(treatment_id),
                "message_id": str(message.id),
                "reminder_key": reminder_key,
                "scheduled_for_present": scheduled_for is not None,
                "channel": message.channel,
                "status": message.status,
            },
        )
    )


async def _reminder_already_queued(
    session: AsyncSession,
    treatment_id: UUID,
    reminder_key: str,
) -> bool:
    result = await session.execute(
        select(AuditLogEntry.id)
        .where(
            AuditLogEntry.event_type == "monitoring_message_queued",
            AuditLogEntry.payload.contains(
                {
                    "treatment_id": str(treatment_id),
                    "reminder_key": reminder_key,
                }
            ),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def _audit_due_monitoring_run(
    session: AsyncSession,
    *,
    processed_count: int,
    queued_count: int,
    skipped_count: int,
    limit: int,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="monitoring_due_run_completed",
            resource_type="system",
            resource_id=SYSTEM_RESOURCE_ID,
            # Keep aggregate worker audits free of treatment, medication, and
            # message text. Per-message audit rows hold the workflow marker.
            payload={
                "processed_count": processed_count,
                "queued_count": queued_count,
                "skipped_count": skipped_count,
                "limit": limit,
            },
        )
    )


def reminder_key_for_slot(reminder: ReminderSlot) -> str:
    """Return the stable audit key shared by monitoring and completion checks."""
    return (
        f"{reminder.medication_id}:"
        f"{_serialise_offset(reminder.offset_from_start)}:"
        f"{reminder.human_label}"
    )


def _serialise_offset(offset: timedelta) -> str:
    seconds = int(offset.total_seconds())
    if seconds == 0:
        return "PT0S"
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, seconds = divmod(remainder, 60)
    date_part = f"{days}D" if days else ""
    time_part = "".join(
        [
            f"{hours}H" if hours else "",
            f"{minutes}M" if minutes else "",
            f"{seconds}S" if seconds else "",
        ]
    )
    if time_part:
        return f"{sign}P{date_part}T{time_part}"
    return f"{sign}P{date_part}"


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
