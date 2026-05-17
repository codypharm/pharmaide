"""Existing-patient lookup used before attaching another treatment."""

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import PatientList, PatientView
from app.db.models import Patient


async def search_patients(
    session: AsyncSession,
    *,
    query: str,
    limit: int,
    offset: int,
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

    result = await session.scalars(
        select(Patient)
        .where(or_(*conditions))
        .order_by(Patient.name.asc(), Patient.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return PatientList(items=[PatientView.model_validate(patient) for patient in result.all()])


def _compact_phone_query(query: str) -> str:
    return "".join(character for character in query if character.isdigit() or character == "+")
