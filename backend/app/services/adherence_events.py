"""Medication adherence event service.

Adherence events are append-only observations about planned reminders: taken,
missed, held, or skipped. They intentionally stay separate from generated
schedule previews so planned dosing and real-world patient behavior do not get
collapsed into one state.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import AdherenceEventCreate, AdherenceEventList, AdherenceEventView
from app.db.models import AdherenceEvent, AuditLogEntry, Medication, Treatment

log = structlog.get_logger(__name__)


class TreatmentNotFound(Exception):
    """Raised when an adherence event references a missing treatment."""


class MedicationNotFound(Exception):
    """Raised when a medication is missing or does not belong to the treatment."""


async def create_adherence_event(
    session: AsyncSession,
    treatment_id: UUID,
    request: AdherenceEventCreate,
) -> AdherenceEventView:
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    medication = await _medication_for_treatment(session, treatment_id, request.medication_id)
    if medication is None:
        raise MedicationNotFound()

    event = AdherenceEvent(
        treatment_id=treatment_id,
        medication_id=request.medication_id,
        status=request.status,
        source=request.source,
        scheduled_for=request.scheduled_for,
        occurred_at=request.occurred_at,
        note=request.note,
    )
    session.add(event)
    await session.flush()

    session.add(
        AuditLogEntry(
            event_type="adherence_event_recorded",
            resource_type="adherence_event",
            resource_id=event.id,
            # Notes can contain patient context. Audit only enough metadata to
            # trace the event without duplicating patient-provided text.
            payload={
                "treatment_id": str(treatment_id),
                "medication_id": str(request.medication_id),
                "status": request.status,
                "source": request.source,
                "scheduled_for_present": request.scheduled_for is not None,
                "occurred_at_present": request.occurred_at is not None,
                "note_present": request.note is not None,
            },
        )
    )
    await session.flush()

    log.info(
        "adherence_event_recorded",
        treatment_id=str(treatment_id),
        medication_id=str(request.medication_id),
        adherence_event_id=str(event.id),
        status=request.status,
        source=request.source,
        scheduled_for_present=request.scheduled_for is not None,
        occurred_at_present=request.occurred_at is not None,
        note_present=request.note is not None,
    )
    return AdherenceEventView.model_validate(event)


async def list_adherence_events(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    limit: int,
    offset: int,
) -> AdherenceEventList:
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    result = await session.execute(
        select(AdherenceEvent)
        .where(AdherenceEvent.treatment_id == treatment_id)
        .order_by(AdherenceEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    events = result.scalars().all()
    log.info(
        "adherence_events_listed",
        treatment_id=str(treatment_id),
        count=len(events),
        limit=limit,
        offset=offset,
    )
    return AdherenceEventList(
        items=[AdherenceEventView.model_validate(event) for event in events]
    )


async def _medication_for_treatment(
    session: AsyncSession,
    treatment_id: UUID,
    medication_id: UUID,
) -> Medication | None:
    return await session.scalar(
        select(Medication).where(
            Medication.id == medication_id,
            Medication.treatment_id == treatment_id,
        )
    )
