"""Patient-reported treatment status.

These rows capture what the patient or pharmacist says happened during a
treatment: side effects, lack of improvement, feeling better, missed doses,
or general updates. They are intentionally separate from adherence events so
clinical monitoring does not collapse into dose tracking.
"""

from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PatientCheckInCreate, PatientCheckInList, PatientCheckInView
from app.db.models import AuditLogEntry, PatientCheckIn, Treatment

log = structlog.get_logger(__name__)


class TreatmentNotFound(Exception):
    """Raised when a check-in references a treatment that does not exist."""


async def create_patient_check_in(
    session: AsyncSession,
    treatment_id: UUID,
    request: PatientCheckInCreate,
) -> PatientCheckInView:
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    check_in = PatientCheckIn(
        treatment_id=treatment_id,
        report_type=request.report_type,
        source=request.source,
        message=request.message,
        observed_at=request.observed_at,
    )
    session.add(check_in)
    await session.flush()

    session.add(
        AuditLogEntry(
            event_type="patient_check_in_recorded",
            resource_type="patient_check_in",
            resource_id=check_in.id,
            # The message can contain PHI or symptoms. Audit metadata is enough
            # to trace that a report happened without duplicating patient text.
            payload={
                "treatment_id": str(treatment_id),
                "report_type": request.report_type,
                "source": request.source,
                "observed_at_present": request.observed_at is not None,
            },
        )
    )
    await session.flush()

    log.info(
        "patient_check_in_recorded",
        treatment_id=str(treatment_id),
        check_in_id=str(check_in.id),
        report_type=request.report_type,
        source=request.source,
        observed_at_present=request.observed_at is not None,
    )
    return PatientCheckInView.model_validate(check_in)


async def list_patient_check_ins(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    limit: int,
    offset: int,
) -> PatientCheckInList:
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    result = await session.execute(
        select(PatientCheckIn)
        .where(PatientCheckIn.treatment_id == treatment_id)
        .order_by(PatientCheckIn.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    check_ins = result.scalars().all()
    log.info(
        "patient_check_ins_listed",
        treatment_id=str(treatment_id),
        count=len(check_ins),
        limit=limit,
        offset=offset,
    )
    return PatientCheckInList(
        items=[PatientCheckInView.model_validate(check_in) for check_in in check_ins]
    )
