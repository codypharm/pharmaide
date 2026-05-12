"""Treatment analysis service.

Sprint 3 starts with an inert analysis service: it creates the durable
analysis row and audit trail, but does not run the graph yet.
"""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import AuditLogEntry, Patient, Treatment, TreatmentAnalysis
from app.services.analysis import (
    AnalysisInProgress,
    analyze_treatment,
    create_pending_analysis,
)


async def _create_treatment(db_session: AsyncSession) -> Treatment:
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn="ANALYSIS-001",
        phone="+18005551212",
    )
    db_session.add(patient)
    await db_session.flush()

    treatment = Treatment(
        patient_id=patient.id,
        clinical_objective="Monitor for ACE-inhibitor cough",
    )
    db_session.add(treatment)
    await db_session.flush()
    return treatment


@pytest.mark.usefixtures("postgres_container")
async def test_create_pending_analysis_returns_pending_row(
    db_session: AsyncSession,
) -> None:
    treatment = await _create_treatment(db_session)

    analysis_id = await create_pending_analysis(db_session, treatment.id)

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.treatment_id == treatment.id
    assert analysis.status == "pending"
    assert analysis.started_at is None
    assert analysis.completed_at is None
    assert analysis.result is None
    assert analysis.error_text is None


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_marks_pending_row_running_and_audit(
    db_session: AsyncSession,
) -> None:
    treatment = await _create_treatment(db_session)
    analysis_id = await create_pending_analysis(db_session, treatment.id)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)

    await analyze_treatment(session_factory, analysis_id)

    analysis = await db_session.get(TreatmentAnalysis, analysis_id)
    assert analysis is not None
    assert analysis.status == "running"
    assert analysis.started_at is not None

    audit = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.resource_id == treatment.id)
        )
    ).scalar_one()
    assert audit.event_type == "analysis_started"
    assert audit.resource_type == "treatment"
    assert audit.payload == {
        "treatment_id": str(treatment.id),
        "analysis_id": str(analysis_id),
    }


@pytest.mark.usefixtures("postgres_container")
async def test_analyze_treatment_rejects_second_active_analysis(
    db_session: AsyncSession,
) -> None:
    treatment = await _create_treatment(db_session)
    await create_pending_analysis(db_session, treatment.id)

    with pytest.raises(AnalysisInProgress):
        await create_pending_analysis(db_session, treatment.id)
