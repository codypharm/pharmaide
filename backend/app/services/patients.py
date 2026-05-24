"""Existing-patient lookup used before attaching another treatment."""

from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PatientList, PatientView
from app.db.models import Patient, Treatment


async def search_patients(
    session: AsyncSession,
    *,
    query: str,
    limit: int,
    offset: int,
    scope_id: UUID | None = None,
) -> PatientList:
    """Find patients by name, MRN, or phone without exposing treatment rows."""
    pattern = f"%{query}%"
    conditions = [
        Patient.name.ilike(pattern),
        Patient.mrn.ilike(pattern),
        Patient.phone.ilike(pattern),
    ]
    compact_phone_query = _compact_phone_query(query)
    if compact_phone_query:
        conditions.append(Patient.phone.ilike(f"%{compact_phone_query}%"))

    statement = select(Patient).where(or_(*conditions))
    if scope_id is not None:
        # Patients are scoped through their treatment rows. The subquery keeps
        # patients unique even when a patient has several treatments.
        scoped_patient_ids = select(Treatment.patient_id).where(Treatment.scope_id == scope_id)
        statement = statement.where(Patient.id.in_(scoped_patient_ids))

    result = await session.scalars(
        statement.order_by(Patient.name.asc(), Patient.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return PatientList(items=[PatientView.model_validate(patient) for patient in result.all()])


def _compact_phone_query(query: str) -> str:
    return "".join(character for character in query if character.isdigit() or character == "+")
