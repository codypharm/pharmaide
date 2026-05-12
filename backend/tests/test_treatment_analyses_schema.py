from datetime import date

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Patient, Treatment, TreatmentAnalysis


@pytest.mark.usefixtures("postgres_container")
async def test_treatment_analysis_keeps_history_but_rejects_two_active_rows(
    db_session: AsyncSession,
) -> None:
    patient = Patient(
        name="Analysis Schema",
        dob=date(1970, 1, 1),
        mrn="ANALYSIS-SCHEMA-001",
        phone="+15551234567",
    )
    treatment = Treatment(patient=patient, clinical_objective="Monitor adherence")
    db_session.add(treatment)
    await db_session.flush()

    db_session.add(TreatmentAnalysis(treatment_id=treatment.id, status="completed"))
    db_session.add(TreatmentAnalysis(treatment_id=treatment.id, status="running"))
    await db_session.flush()

    with pytest.raises(IntegrityError):
        async with db_session.begin_nested():
            db_session.add(TreatmentAnalysis(treatment_id=treatment.id, status="pending"))
            await db_session.flush()


@pytest.mark.usefixtures("postgres_container")
async def test_treatment_analysis_rows_cascade_when_treatment_is_deleted(
    db_session: AsyncSession,
) -> None:
    patient = Patient(
        name="Analysis Cascade",
        dob=date(1970, 1, 1),
        mrn="ANALYSIS-SCHEMA-002",
        phone="+15557654321",
    )
    treatment = Treatment(patient=patient, clinical_objective="Monitor adherence")
    db_session.add(treatment)
    await db_session.flush()

    analysis = TreatmentAnalysis(treatment_id=treatment.id, status="completed")
    db_session.add(analysis)
    await db_session.flush()

    await db_session.execute(delete(Treatment).where(Treatment.id == treatment.id))
    await db_session.flush()

    result = await db_session.execute(
        select(TreatmentAnalysis).where(TreatmentAnalysis.id == analysis.id)
    )
    assert result.scalar_one_or_none() is None
