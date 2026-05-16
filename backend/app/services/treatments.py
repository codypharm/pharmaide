"""Treatment ingestion service.

Owns the single transaction that creates patient + treatment + medications
+ audit row. Routes are thin translators around this; tests of the full
flow exercise this function directly via db_session.
"""

from uuid import UUID

import phonenumbers
import structlog
from sqlalchemy import select
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
from app.db.models import AuditLogEntry, Medication, Patient, Treatment

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


class TreatmentNotFound(Exception):
    """Raised when a treatment-specific command references an unknown treatment."""


async def create_treatment(
    session: AsyncSession, request: CreateTreatmentRequest
) -> CreateTreatmentResponse:
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
    session: AsyncSession, limit: int, offset: int
) -> TreatmentList:
    # selectinload pre-fetches patient + medications in batched queries so
    # the list-row mapping below stays sync — no N+1, no awaits in the loop.
    result = await session.execute(
        select(Treatment)
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
    return TreatmentList(items=items)


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
