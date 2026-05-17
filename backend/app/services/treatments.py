"""Treatment ingestion service.

Owns the single transaction that creates patient + treatment + medications
+ audit row. Routes are thin translators around this; tests of the full
flow exercise this function directly via db_session.
"""

from datetime import UTC, datetime
from uuid import UUID

import phonenumbers
import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    ChatResponseMode,
    CreateTreatmentRequest,
    CreateTreatmentResponse,
    MedicationView,
    PatientView,
    TreatmentDetail,
    TreatmentList,
    TreatmentListItem,
    TreatmentView,
)
from app.db.models import AuditLogEntry, Medication, Patient, Treatment, TreatmentAnalysis

log = structlog.get_logger(__name__)


def _to_e164(rfc3966_phone: str) -> str:
    """Convert pydantic's RFC3966 form ("tel:+1-800-555-1212") to E.164.

    WhatsApp Business API rejects anything but strict E.164. Store the
    canonical form so consumers don't each have to re-normalise.
    """
    parsed = phonenumbers.parse(rfc3966_phone)
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class MRNConflict(Exception):
    """Raised when a patient with the requested MRN already exists."""


class PatientNotFound(Exception):
    """Raised when a treatment is attached to a missing patient."""


class TreatmentNotFound(Exception):
    """Raised when a treatment-specific command references an unknown treatment."""


class AnalysisNotCompleted(Exception):
    """Raised when monitoring is requested before clinical analysis is ready."""


class TreatmentNotCompleted(Exception):
    """Raised when a completion-only command targets an unfinished treatment."""


class TreatmentAlreadyCompleted(Exception):
    """Raised when a terminal command would rewrite a completed course."""


async def create_treatment(
    session: AsyncSession, request: CreateTreatmentRequest
) -> CreateTreatmentResponse:
    patient = await _resolve_treatment_patient(session, request)

    treatment = Treatment(
        patient_id=patient.id,
        clinical_objective=request.treatment.clinical_objective,
        treatment_start_at=request.treatment.treatment_start_at,
    )
    session.add(treatment)
    await session.flush()

    medications = [
        Medication(
            treatment_id=treatment.id,
            name=med.name,
            dosage=med.dosage,
            frequency=med.frequency,
            duration=med.duration,
            objective=med.objective,
            ordinal=ordinal,
        )
        for ordinal, med in enumerate(request.medications)
    ]
    session.add_all(medications)
    await session.flush()

    audit = AuditLogEntry(
        event_type="treatment_created",
        resource_type="treatment",
        resource_id=treatment.id,
        # Per HIPAA "minimum necessary" — IDs and a non-PHI summary only.
        # No name, dob, mrn, phone, allergy names, dosages, frequencies, durations.
        payload={
            "patient_id": str(patient.id),
            "treatment_id": str(treatment.id),
            "medication_count": len(medications),
            "medication_names": [m.name for m in medications],
            "allergy_count": len(patient.allergies),
            "treatment_start_at_present": request.treatment.treatment_start_at is not None,
            "ingestion_method": request.ingestion_method,
            "clinical_objective_present": request.treatment.clinical_objective is not None,
        },
    )
    session.add(audit)
    await session.flush()

    return CreateTreatmentResponse(treatment_id=treatment.id, patient_id=patient.id)


async def _resolve_treatment_patient(
    session: AsyncSession, request: CreateTreatmentRequest
) -> Patient:
    if request.patient_id is not None:
        patient = await session.get(Patient, request.patient_id)
        if patient is None:
            raise PatientNotFound()
        return patient

    assert request.patient is not None
    patient = Patient(
        name=request.patient.name,
        dob=request.patient.dob,
        mrn=request.patient.mrn,
        phone=_to_e164(str(request.patient.phone)),
        allergies=request.patient.allergies,
    )
    session.add(patient)
    try:
        await session.flush()
    except IntegrityError as exc:
        # mrn UNIQUE is the only constraint that can fire here right now.
        # Re-raise as a domain-typed exception the route translates to 409.
        raise MRNConflict() from exc
    return patient


async def get_treatment(session: AsyncSession, treatment_id: UUID) -> TreatmentDetail | None:
    result = await session.execute(
        select(Treatment)
        .where(Treatment.id == treatment_id)
        .options(selectinload(Treatment.patient), selectinload(Treatment.medications))
    )
    treatment = result.scalar_one_or_none()
    if treatment is None:
        return None
    return TreatmentDetail(
        patient=PatientView.model_validate(treatment.patient),
        treatment=TreatmentView.model_validate(treatment),
        medications=[MedicationView.model_validate(m) for m in treatment.medications],
    )


async def treatment_exists(session: AsyncSession, treatment_id: UUID) -> bool:
    result = await session.execute(select(Treatment.id).where(Treatment.id == treatment_id))
    return result.scalar_one_or_none() is not None


async def list_treatments(
    session: AsyncSession,
    limit: int,
    offset: int,
    *,
    status: str | None = None,
    archived: bool | None = None,
) -> TreatmentList:
    # selectinload pre-fetches patient + medications in batched queries so
    # the list-row mapping below stays sync — no N+1, no awaits in the loop.
    statement = select(Treatment)
    if status is not None:
        statement = statement.where(Treatment.status == status)
    if archived is True:
        statement = statement.where(Treatment.archived_at.is_not(None))
    elif archived is False:
        statement = statement.where(Treatment.archived_at.is_(None))

    active_count, completed_count, archived_count = await _count_treatment_directory(session)

    result = await session.execute(
        statement
        .order_by(Treatment.created_at.desc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(Treatment.patient), selectinload(Treatment.medications))
    )
    treatments = result.scalars().all()
    items = [
        TreatmentListItem(
            patient=PatientView.model_validate(t.patient),
            treatment=TreatmentView.model_validate(t),
            medication_count=len(t.medications),
            # Medications are ordered by ordinal; first row is the lead drug.
            first_medication_name=t.medications[0].name if t.medications else None,
        )
        for t in treatments
    ]
    return TreatmentList(
        items=items,
        active_count=active_count,
        completed_count=completed_count,
        archived_count=archived_count,
    )


async def _count_treatment_directory(session: AsyncSession) -> tuple[int, int, int]:
    """Count operational treatment buckets independently of the current page."""
    active_count = await _count_treatments(
        session,
        Treatment.status != "completed",
        Treatment.archived_at.is_(None),
    )
    completed_count = await _count_treatments(
        session,
        Treatment.status == "completed",
        Treatment.archived_at.is_(None),
    )
    archived_count = await _count_treatments(session, Treatment.archived_at.is_not(None))
    return active_count, completed_count, archived_count


async def _count_treatments(session: AsyncSession, *conditions: object) -> int:
    result = await session.execute(
        select(func.count(Treatment.id)).select_from(Treatment).where(*conditions)
    )
    return int(result.scalar_one())


async def update_chat_response_mode(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    chat_response_mode: ChatResponseMode,
) -> TreatmentView:
    """Let pharmacists hand patient replies between AI and manual control."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    old_mode = treatment.chat_response_mode
    treatment.chat_response_mode = chat_response_mode

    if old_mode != chat_response_mode:
        session.add(
            AuditLogEntry(
                event_type="treatment_chat_response_mode_changed",
                resource_type="treatment",
                resource_id=treatment.id,
                # This is workflow state only; conversation text stays in
                # conversation_messages and is not duplicated into audit rows.
                payload={
                    "old_chat_response_mode": old_mode,
                    "new_chat_response_mode": chat_response_mode,
                    "automation_mode": treatment.automation_mode,
                    "trigger": "manual_pharmacist_control",
                },
            )
        )
        log.info(
            "treatment_chat_response_mode_changed",
            treatment_id=str(treatment.id),
            old_chat_response_mode=old_mode,
            new_chat_response_mode=chat_response_mode,
            automation_mode=treatment.automation_mode,
            trigger="manual_pharmacist_control",
        )

    await session.flush()
    return TreatmentView.model_validate(treatment)


async def start_treatment_cycle(session: AsyncSession, treatment_id: UUID) -> TreatmentView:
    """Activate monitoring for a treatment after pharmacist review."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    old_status = treatment.status
    if old_status != "active":
        analysis = await _latest_completed_analysis(session, treatment_id)
        if analysis is None:
            raise AnalysisNotCompleted()

        treatment.status = "active"
        session.add(
            AuditLogEntry(
                event_type="treatment_cycle_started",
                resource_type="treatment",
                resource_id=treatment.id,
                # WhatsApp onboarding is intentionally not sent in this slice;
                # audit the workflow state without patient or medication text.
                payload={
                    "old_status": old_status,
                    "new_status": "active",
                    "analysis_id": str(analysis.id),
                    "onboarding_delivery": "not_configured",
                },
            )
        )
        log.info(
            "treatment_cycle_started",
            treatment_id=str(treatment.id),
            old_status=old_status,
            new_status="active",
            analysis_id=str(analysis.id),
            onboarding_delivery="not_configured",
        )

    await session.flush()
    return TreatmentView.model_validate(treatment)


async def archive_treatment(session: AsyncSession, treatment_id: UUID) -> TreatmentView:
    """Move a completed treatment out of active work queues."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.status != "completed":
        raise TreatmentNotCompleted()
    if treatment.archived_at is not None:
        return TreatmentView.model_validate(treatment)

    treatment.archived_at = datetime.now(UTC)
    session.add(
        AuditLogEntry(
            event_type="treatment_archived",
            resource_type="treatment",
            resource_id=treatment.id,
            # Archive audit records workflow state only, not patient or drug text.
            payload={
                "status": treatment.status,
                "already_archived": False,
            },
        )
    )
    log.info(
        "treatment_archived",
        treatment_id=str(treatment.id),
        status=treatment.status,
    )

    await session.flush()
    return TreatmentView.model_validate(treatment)


async def terminate_treatment(session: AsyncSession, treatment_id: UUID) -> TreatmentView:
    """Stop monitoring for a pending or active treatment before normal completion."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.status == "completed":
        raise TreatmentAlreadyCompleted()
    if treatment.status == "terminated":
        return TreatmentView.model_validate(treatment)

    old_status = treatment.status
    old_automation_mode = treatment.automation_mode
    treatment.status = "terminated"
    treatment.automation_mode = "paused"
    session.add(
        AuditLogEntry(
            event_type="treatment_terminated",
            resource_type="treatment",
            resource_id=treatment.id,
            # Termination audit records workflow state only. Reason text can
            # contain patient context, so it is intentionally left out here.
            payload={
                "old_status": old_status,
                "new_status": treatment.status,
                "old_automation_mode": old_automation_mode,
                "new_automation_mode": treatment.automation_mode,
                "already_terminated": False,
            },
        )
    )
    log.info(
        "treatment_terminated",
        treatment_id=str(treatment.id),
        old_status=old_status,
        new_status=treatment.status,
        old_automation_mode=old_automation_mode,
        new_automation_mode=treatment.automation_mode,
    )

    await session.flush()
    return TreatmentView.model_validate(treatment)


async def _latest_completed_analysis(
    session: AsyncSession, treatment_id: UUID
) -> TreatmentAnalysis | None:
    result = await session.execute(
        select(TreatmentAnalysis)
        .where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status == "completed",
        )
        .order_by(TreatmentAnalysis.created_at.desc())
    )
    return next((analysis for analysis in result.scalars() if analysis.result is not None), None)


async def update_clinical_objective(
    session: AsyncSession,
    treatment_id: UUID,
    *,
    clinical_objective: str | None,
) -> TreatmentView:
    """Update pharmacist-maintained monitoring intent without auditing the text."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    old_objective = treatment.clinical_objective
    treatment.clinical_objective = clinical_objective

    if old_objective != clinical_objective:
        session.add(
            AuditLogEntry(
                event_type="treatment_clinical_objective_changed",
                resource_type="treatment",
                resource_id=treatment.id,
                # The objective can reveal patient condition. Audit presence
                # transitions only; the current value remains on treatment.
                payload={
                    "old_clinical_objective_present": old_objective is not None,
                    "new_clinical_objective_present": clinical_objective is not None,
                },
            )
        )
        log.info(
            "treatment_clinical_objective_changed",
            treatment_id=str(treatment.id),
            old_clinical_objective_present=old_objective is not None,
            new_clinical_objective_present=clinical_objective is not None,
        )

    await session.flush()
    return TreatmentView.model_validate(treatment)
