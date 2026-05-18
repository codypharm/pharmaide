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

from app.agents.analysis_schemas import AnalysisResult
from app.api.schemas import AdherenceEventCreate
from app.db.models import (
    AdherenceEvent,
    AuditLogEntry,
    ConversationMessage,
    Medication,
    Treatment,
    TreatmentAnalysis,
)
from app.services.adherence_events import create_adherence_event
from app.services.course_completion import complete_treatment_course_if_finished
from app.services.schedule_keys import reminder_key_for_slot
from app.services.triage import create_open_triage_item

log = structlog.get_logger(__name__)
SYSTEM_RESOURCE_ID = UUID("00000000-0000-0000-0000-000000000000")
NON_RESPONSE_GRACE_PERIOD = timedelta(hours=4)
ADHERENCE_NUDGE = (
    "Taking it close to the planned time helps you stay on track. "
    "Reply when taken, or tell us if you feel unwell, are unsure, "
    "or are having trouble with this dose."
)


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
        queue_marker = await _load_reminder_queue_marker(session, treatment_id, reminder_key)
        if queue_marker is not None:
            await _record_non_response_if_needed(
                session,
                treatment_id=treatment_id,
                medication_id=medication.id,
                reminder_key=reminder_key,
                scheduled_for=scheduled_for,
                current_time=current_time,
                queue_marker=queue_marker,
            )
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
    await complete_treatment_course_if_finished(
        session,
        treatment_id=treatment_id,
        now=current_time,
    )
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
            f"{ADHERENCE_NUDGE}"
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


async def _load_reminder_queue_marker(
    session: AsyncSession,
    treatment_id: UUID,
    reminder_key: str,
) -> AuditLogEntry | None:
    result = await session.execute(
        select(AuditLogEntry)
        .where(
            AuditLogEntry.event_type == "monitoring_message_queued",
            AuditLogEntry.payload.contains(
                {
                    "treatment_id": str(treatment_id),
                    "reminder_key": reminder_key,
                }
            ),
        )
        .order_by(AuditLogEntry.created_at.desc(), AuditLogEntry.id.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _record_non_response_if_needed(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    medication_id: UUID,
    reminder_key: str,
    scheduled_for: datetime,
    current_time: datetime,
    queue_marker: AuditLogEntry,
) -> bool:
    if _aware_utc(queue_marker.created_at) + NON_RESPONSE_GRACE_PERIOD > current_time:
        return False
    if await _patient_reply_already_captured(
        session,
        treatment_id=treatment_id,
        reminder_key=reminder_key,
    ):
        return False
    if await _adherence_event_already_recorded(
        session,
        treatment_id=treatment_id,
        medication_id=medication_id,
        scheduled_for=scheduled_for,
    ):
        return False
    if await _non_response_already_recorded(
        session,
        treatment_id=treatment_id,
        reminder_key=reminder_key,
    ):
        return False

    event = await create_adherence_event(
        session,
        treatment_id,
        AdherenceEventCreate(
            medication_id=medication_id,
            status="missed",
            source="system",
            scheduled_for=scheduled_for,
            occurred_at=current_time,
        ),
    )
    triage_item = await create_open_triage_item(
        session,
        treatment_id=treatment_id,
        conversation_message_id=_queue_marker_message_id(queue_marker),
        reason="non_responsive",
    )
    _audit_non_response(
        session,
        treatment_id=treatment_id,
        adherence_event_id=event.id,
        triage_item_id=triage_item.id,
        reminder_key=reminder_key,
        scheduled_for=scheduled_for,
    )
    log.info(
        "monitoring_non_response_recorded",
        treatment_id=str(treatment_id),
        adherence_event_id=str(event.id),
        triage_item_id=str(triage_item.id),
        reminder_key=reminder_key,
    )
    return True


async def _patient_reply_already_captured(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    reminder_key: str,
) -> bool:
    result = await session.execute(
        select(AuditLogEntry.id)
        .where(
            AuditLogEntry.event_type == "patient_reply_adherence_captured",
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


async def _adherence_event_already_recorded(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    medication_id: UUID,
    scheduled_for: datetime,
) -> bool:
    result = await session.execute(
        select(AdherenceEvent.id)
        .where(
            AdherenceEvent.treatment_id == treatment_id,
            AdherenceEvent.medication_id == medication_id,
            AdherenceEvent.scheduled_for == scheduled_for,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _non_response_already_recorded(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    reminder_key: str,
) -> bool:
    result = await session.execute(
        select(AuditLogEntry.id)
        .where(
            AuditLogEntry.event_type == "monitoring_non_response_recorded",
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


def _audit_non_response(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    adherence_event_id: UUID,
    triage_item_id: UUID,
    reminder_key: str,
    scheduled_for: datetime,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="monitoring_non_response_recorded",
            resource_type="adherence_event",
            resource_id=adherence_event_id,
            # No patient message or medication text here; the reminder key is
            # enough to correlate the workflow without duplicating PHI.
            payload={
                "treatment_id": str(treatment_id),
                "adherence_event_id": str(adherence_event_id),
                "triage_item_id": str(triage_item_id),
                "reminder_key": reminder_key,
                "scheduled_for_present": scheduled_for is not None,
                "status": "missed",
                "source": "system",
            },
        )
    )


def _queue_marker_message_id(queue_marker: AuditLogEntry) -> UUID | None:
    message_id = queue_marker.payload.get("message_id")
    if not isinstance(message_id, str):
        return None
    try:
        return UUID(message_id)
    except ValueError:
        return None


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


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
