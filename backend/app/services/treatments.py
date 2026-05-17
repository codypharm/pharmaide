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
    MedicationCreate,
    MedicationView,
    PatientView,
    TreatmentDetail,
    TreatmentList,
    TreatmentListItem,
    TreatmentView,
)
from app.db.models import (
    AuditLogEntry,
    ConversationMessage,
    Medication,
    Patient,
    Treatment,
    TreatmentAnalysis,
)

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


class MedicationNotFound(Exception):
    """Raised when a medication command references the wrong treatment."""


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

        old_automation_mode = treatment.automation_mode
        treatment.status = "active"
        treatment.automation_mode = "active"
        onboarding_message = _build_cycle_onboarding_message(treatment_id=treatment.id)
        session.add(onboarding_message)
        await session.flush()
        session.add(
            AuditLogEntry(
                event_type="treatment_cycle_started",
                resource_type="treatment",
                resource_id=treatment.id,
                # The patient-facing body may become configurable later. Keep
                # audit payloads to routing/state metadata only.
                payload={
                    "old_status": old_status,
                    "new_status": "active",
                    "old_automation_mode": old_automation_mode,
                    "new_automation_mode": treatment.automation_mode,
                    "analysis_id": str(analysis.id),
                    "onboarding_delivery": "queued",
                    "onboarding_message_id": str(onboarding_message.id),
                },
            )
        )
        log.info(
            "treatment_cycle_started",
            treatment_id=str(treatment.id),
            old_status=old_status,
            new_status="active",
            old_automation_mode=old_automation_mode,
            new_automation_mode=treatment.automation_mode,
            analysis_id=str(analysis.id),
            onboarding_delivery="queued",
            onboarding_message_id=str(onboarding_message.id),
        )

    await session.flush()
    return TreatmentView.model_validate(treatment)


def _build_cycle_onboarding_message(*, treatment_id: UUID) -> ConversationMessage:
    """Create the first patient-facing message when monitoring begins."""
    return ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body=(
            "Your pharmacist has started monitoring this treatment. "
            "I will send medication reminders and check in on how you are doing."
        ),
    )


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


async def discontinue_medication(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    medication_id: UUID,
) -> MedicationView:
    """Discontinue one medication and require fresh analysis before monitoring resumes."""
    medication = await _get_treatment_medication(session, treatment_id, medication_id)
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()

    already_discontinued = medication.discontinued_at is not None
    old_status = treatment.status
    old_automation_mode = treatment.automation_mode
    superseded_count = 0

    if not already_discontinued:
        medication.discontinued_at = datetime.now(UTC)
        active_medication_count = await _count_active_medications(session, treatment_id)
        treatment.status = "terminated" if active_medication_count == 0 else "pending"
        treatment.automation_mode = "paused"
        superseded_count = await _supersede_existing_analyses(session, treatment_id)
        cancelled_message_count = await _cancel_queued_reminders(session, treatment_id)
        patient_notification = _build_medication_discontinued_message(
            treatment_id=treatment_id,
            medication=medication,
            active_medication_count=active_medication_count,
        )
        session.add(patient_notification)
        await session.flush()
        _audit_medication_discontinued(
            session,
            medication=medication,
            treatment=treatment,
            old_status=old_status,
            old_automation_mode=old_automation_mode,
            superseded_count=superseded_count,
            active_medication_count=active_medication_count,
            cancelled_message_count=cancelled_message_count,
            patient_notification=patient_notification,
        )
        log.info(
            "treatment_medication_discontinued",
            treatment_id=str(treatment_id),
            medication_id=str(medication_id),
            old_status=old_status,
            new_status=treatment.status,
            old_automation_mode=old_automation_mode,
            new_automation_mode=treatment.automation_mode,
            superseded_analysis_count=superseded_count,
            active_medication_count=active_medication_count,
            cancelled_queued_message_count=cancelled_message_count,
            patient_notification_message_id=str(patient_notification.id),
        )

    await session.flush()
    return MedicationView.model_validate(medication)


async def add_medication_to_treatment(
    session: AsyncSession,
    *,
    treatment_id: UUID,
    medication: MedicationCreate,
) -> MedicationView:
    """Add a medication and force pharmacist review before monitoring resumes."""
    treatment = await session.get(Treatment, treatment_id)
    if treatment is None:
        raise TreatmentNotFound()
    if treatment.status in {"completed", "terminated"}:
        raise TreatmentAlreadyCompleted()

    old_status = treatment.status
    old_automation_mode = treatment.automation_mode
    new_medication = Medication(
        treatment_id=treatment.id,
        name=medication.name,
        dosage=medication.dosage,
        frequency=medication.frequency,
        duration=medication.duration,
        objective=medication.objective,
        ordinal=await _next_medication_ordinal(session, treatment.id),
    )
    session.add(new_medication)
    await session.flush()

    treatment.status = "pending"
    treatment.automation_mode = "paused"
    superseded_count = await _supersede_existing_analyses(session, treatment.id)
    cancelled_message_count = await _cancel_queued_reminders(session, treatment.id)
    active_medication_count = await _count_active_medications(session, treatment.id)
    patient_notification = None
    if old_status == "active":
        patient_notification = _build_medication_added_message(
            treatment_id=treatment.id,
            medication=new_medication,
        )
        session.add(patient_notification)
    await session.flush()
    _audit_medication_added(
        session,
        medication=new_medication,
        treatment=treatment,
        old_status=old_status,
        old_automation_mode=old_automation_mode,
        superseded_count=superseded_count,
        active_medication_count=active_medication_count,
        cancelled_message_count=cancelled_message_count,
        patient_notification=patient_notification,
    )
    log.info(
        "treatment_medication_added",
        treatment_id=str(treatment.id),
        medication_id=str(new_medication.id),
        old_status=old_status,
        new_status=treatment.status,
        old_automation_mode=old_automation_mode,
        new_automation_mode=treatment.automation_mode,
        superseded_analysis_count=superseded_count,
        active_medication_count=active_medication_count,
        cancelled_queued_message_count=cancelled_message_count,
        patient_notification_message_id=(
            str(patient_notification.id) if patient_notification is not None else None
        ),
    )

    await session.flush()
    return MedicationView.model_validate(new_medication)


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


async def _get_treatment_medication(
    session: AsyncSession,
    treatment_id: UUID,
    medication_id: UUID,
) -> Medication:
    result = await session.execute(
        select(Medication).where(
            Medication.id == medication_id,
            Medication.treatment_id == treatment_id,
        )
    )
    medication = result.scalar_one_or_none()
    if medication is None:
        raise MedicationNotFound()
    return medication


async def _next_medication_ordinal(session: AsyncSession, treatment_id: UUID) -> int:
    result = await session.execute(
        select(func.max(Medication.ordinal)).where(Medication.treatment_id == treatment_id)
    )
    max_ordinal = result.scalar_one()
    return 0 if max_ordinal is None else int(max_ordinal) + 1


async def _supersede_existing_analyses(session: AsyncSession, treatment_id: UUID) -> int:
    result = await session.execute(
        select(TreatmentAnalysis).where(
            TreatmentAnalysis.treatment_id == treatment_id,
            TreatmentAnalysis.status.in_(("pending", "running", "completed", "failed")),
        )
    )
    analyses = list(result.scalars())
    for analysis in analyses:
        analysis.status = "superseded"
        analysis.completed_at = func.clock_timestamp()
    return len(analyses)


async def _count_active_medications(session: AsyncSession, treatment_id: UUID) -> int:
    result = await session.execute(
        select(Medication.id).where(
            Medication.treatment_id == treatment_id,
            Medication.discontinued_at.is_(None),
        )
    )
    return len(list(result.scalars()))


async def _cancel_queued_reminders(session: AsyncSession, treatment_id: UUID) -> int:
    result = await session.execute(
        select(ConversationMessage).where(
            ConversationMessage.treatment_id == treatment_id,
            ConversationMessage.direction == "outbound",
            ConversationMessage.sender_type == "assistant",
            ConversationMessage.channel == "whatsapp",
            ConversationMessage.status == "queued",
            ConversationMessage.body.like("Reminder:%"),
        )
    )
    messages = list(result.scalars())
    for message in messages:
        message.status = "cancelled"
    return len(messages)


def _build_medication_discontinued_message(
    *,
    treatment_id: UUID,
    medication: Medication,
    active_medication_count: int,
) -> ConversationMessage:
    if active_medication_count == 0:
        body = (
            "Your pharmacist has updated your treatment plan. There are no active medications "
            "left for this monitoring cycle. Please follow your pharmacist's latest instructions."
        )
    else:
        body = (
            "Your pharmacist has updated your treatment plan. "
            f"Please stop taking {medication.name} "
            "unless your pharmacist has told you otherwise. Reminders are paused while your "
            "pharmacist reviews the updated plan."
        )
    return ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body=body,
    )


def _build_medication_added_message(
    *,
    treatment_id: UUID,
    medication: Medication,
) -> ConversationMessage:
    return ConversationMessage(
        treatment_id=treatment_id,
        direction="outbound",
        sender_type="assistant",
        channel="whatsapp",
        status="queued",
        body=(
            "Your pharmacist has updated your treatment plan. "
            f"{medication.name} has been added. "
            "Please follow your pharmacist's direct instructions for this medication. "
            "Reminders are paused while your pharmacist reviews the updated plan."
        ),
    )


def _audit_medication_added(
    session: AsyncSession,
    *,
    medication: Medication,
    treatment: Treatment,
    old_status: str,
    old_automation_mode: str,
    superseded_count: int,
    active_medication_count: int,
    cancelled_message_count: int,
    patient_notification: ConversationMessage | None,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="treatment_medication_added",
            resource_type="medication",
            resource_id=medication.id,
            # Medication text can contain PHI-like freeform details, so audit
            # only records workflow metadata and stable IDs.
            payload={
                "treatment_id": str(treatment.id),
                "medication_id": str(medication.id),
                "old_treatment_status": old_status,
                "new_treatment_status": treatment.status,
                "old_automation_mode": old_automation_mode,
                "new_automation_mode": treatment.automation_mode,
                "superseded_analysis_count": superseded_count,
                "active_medication_count": active_medication_count,
                "cancelled_queued_message_count": cancelled_message_count,
                "patient_notification_message_id": (
                    str(patient_notification.id) if patient_notification is not None else None
                ),
            },
        )
    )


def _audit_medication_discontinued(
    session: AsyncSession,
    *,
    medication: Medication,
    treatment: Treatment,
    old_status: str,
    old_automation_mode: str,
    superseded_count: int,
    active_medication_count: int,
    cancelled_message_count: int,
    patient_notification: ConversationMessage,
) -> None:
    session.add(
        AuditLogEntry(
            event_type="treatment_medication_discontinued",
            resource_type="medication",
            resource_id=medication.id,
            # Medication names, doses, and objectives stay out of audit payloads.
            payload={
                "treatment_id": str(treatment.id),
                "medication_id": str(medication.id),
                "old_treatment_status": old_status,
                "new_treatment_status": treatment.status,
                "old_automation_mode": old_automation_mode,
                "new_automation_mode": treatment.automation_mode,
                "superseded_analysis_count": superseded_count,
                "active_medication_count": active_medication_count,
                "cancelled_queued_message_count": cancelled_message_count,
                "patient_notification_message_id": str(patient_notification.id),
                "already_discontinued": False,
            },
        )
    )


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
