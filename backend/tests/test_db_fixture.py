"""Smoke test for the db_session fixture itself.

Confirms testcontainers brings up Postgres, migrations apply, and per-test
transactional rollback works — the foundation every Sprint 2+ DB test
relies on.
"""

from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Patient


@pytest.mark.usefixtures("postgres_container")
async def test_db_session_fixture_round_trips_a_row(db_session: AsyncSession) -> None:
    patient = Patient(
        name="Smoke Test",
        dob=date(1990, 1, 1),
        mrn="SMOKE-001",
        phone="+15551234567",
    )
    db_session.add(patient)
    await db_session.flush()

    result = await db_session.execute(select(Patient).where(Patient.mrn == "SMOKE-001"))
    fetched = result.scalar_one()
    assert fetched.name == "Smoke Test"
    assert fetched.id is not None  # server-generated UUID
    assert fetched.created_at is not None  # server-generated timestamp


@pytest.mark.usefixtures("postgres_container")
async def test_db_session_rollback_isolates_tests(db_session: AsyncSession) -> None:
    """If the previous test's row leaks into this one, this fails."""
    result = await db_session.execute(select(Patient).where(Patient.mrn == "SMOKE-001"))
    assert result.scalar_one_or_none() is None
