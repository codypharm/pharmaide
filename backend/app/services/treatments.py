"""Treatment ingestion service.

Owns the single transaction that creates patient + treatment + medications
+ audit row. Routes are thin translators around this; tests of the full
flow exercise this function directly via db_session.
"""

from uuid import UUID

import phonenumbers
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas import (
    CreateTreatmentRequest,
    CreateTreatmentResponse,
    MedicationView,
    PatientView,
    TreatmentDetail,
    TreatmentView,
)
from app.db.models import AuditLogEntry, Medication, Patient, Treatment


def _to_e164(rfc3966_phone: str) -> str:
    """Convert pydantic's RFC3966 form ("tel:+1-800-555-1212") to E.164.

    WhatsApp Business API rejects anything but strict E.164. Store the
    canonical form so consumers don't each have to re-normalise.
    """
    parsed = phonenumbers.parse(rfc3966_phone)
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


class MRNConflict(Exception):
    """Raised when a patient with the requested MRN already exists."""


async def create_treatment(
    session: AsyncSession, request: CreateTreatmentRequest
) -> CreateTreatmentResponse:
    patient = Patient(
        name=request.patient.name,
        dob=request.patient.dob,
        mrn=request.patient.mrn,
        phone=_to_e164(str(request.patient.phone)),
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
        # No name, dob, mrn, phone, dosages, frequencies, durations.
        payload={
            "patient_id": str(patient.id),
            "treatment_id": str(treatment.id),
            "medication_count": len(medications),
            "medication_names": [m.name for m in medications],
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
