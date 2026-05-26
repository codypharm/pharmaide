"""Internal maintenance endpoints."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry, ConversationMessage, Patient, Treatment
from app.services import dailymed_cache, task_runner

_DEFAULT_ARCHIVED_AT = object()


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_checkpoints_endpoint_logs_non_phi_audit(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        task_runner,
        "cleanup_checkpoints",
        lambda checkpoint_db_path, max_age_days=7: task_runner.CheckpointCleanupResult(
            deleted_count=2,
            freed_mb=1.25,
        ),
    )

    response = await app_client.post("/internal/cleanup/checkpoints")

    assert response.status_code == 200
    assert response.json() == {"deleted_count": 2, "freed_mb": 1.25}

    audit = (
        await db_session.execute(
            select(AuditLogEntry).where(AuditLogEntry.event_type == "checkpoints_cleaned")
        )
    ).scalar_one()
    assert audit.resource_type == "system"
    assert audit.resource_id == UUID("00000000-0000-0000-0000-000000000000")
    assert audit.payload == {
        "deleted_count": 2,
        "freed_mb": 1.25,
        "max_age_days": 7,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_dailymed_cache_endpoint_returns_deleted_count(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _cleanup_failed_dailymed_cache(
        _session: object,
        *,
        retention_days: int = dailymed_cache.DAILYMED_FAILED_CACHE_RETENTION_DAYS,
    ) -> int:
        assert retention_days == dailymed_cache.DAILYMED_FAILED_CACHE_RETENTION_DAYS
        return 3

    monkeypatch.setattr(
        dailymed_cache,
        "cleanup_failed_dailymed_cache",
        _cleanup_failed_dailymed_cache,
    )

    response = await app_client.post("/internal/cleanup/dailymed-cache")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_count": 3,
        "retention_days": dailymed_cache.DAILYMED_FAILED_CACHE_RETENTION_DAYS,
    }


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_closed_treatments_dry_run_does_not_delete_rows(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    treatment = await _persist_archived_closed_treatment(db_session, mrn="RETENTION-DRY")

    response = await app_client.post(
        "/internal/cleanup/closed-treatments",
        json={"dry_run": True, "retention_days": 30},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "dry_run": True,
        "retention_days": 30,
        "eligible_treatment_count": 1,
        "deleted_treatment_count": 0,
        "deleted_patient_count": 0,
        "deleted_audit_log_count": 0,
    }
    assert await db_session.get(Treatment, treatment.id) is not None
    assert await db_session.get(Patient, treatment.patient_id) is not None

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "closed_treatments_retention_cleanup"
        )
    )
    assert audit is not None
    assert audit.payload["dry_run"] is True
    assert "Eleanor" not in str(audit.payload)


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_closed_treatments_deletes_archived_closed_lifecycle_data(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    eligible = await _persist_archived_closed_treatment(db_session, mrn="RETENTION-APPLY")
    visible_completed = await _persist_archived_closed_treatment(
        db_session,
        mrn="RETENTION-VISIBLE",
        archived_at=None,
    )
    recent_archived = await _persist_archived_closed_treatment(
        db_session,
        mrn="RETENTION-RECENT",
        archived_at=datetime.now(UTC) - timedelta(days=5),
    )

    response = await app_client.post(
        "/internal/cleanup/closed-treatments",
        json={"dry_run": False, "retention_days": 30},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "dry_run": False,
        "retention_days": 30,
        "eligible_treatment_count": 1,
        "deleted_treatment_count": 1,
        "deleted_patient_count": 1,
        "deleted_audit_log_count": 1,
    }
    assert await db_session.get(Treatment, eligible.id) is None
    assert await db_session.get(Patient, eligible.patient_id) is None
    assert await db_session.get(Treatment, visible_completed.id) is not None
    assert await db_session.get(Treatment, recent_archived.id) is not None
    assert await db_session.scalar(
        select(ConversationMessage).where(ConversationMessage.treatment_id == eligible.id)
    ) is None


async def _persist_archived_closed_treatment(
    session: AsyncSession,
    *,
    mrn: str,
    archived_at: datetime | None | object = _DEFAULT_ARCHIVED_AT,
) -> Treatment:
    effective_archived_at = (
        datetime.now(UTC) - timedelta(days=60)
        if archived_at is _DEFAULT_ARCHIVED_AT
        else archived_at
    )
    patient = Patient(
        name="Eleanor Vance",
        dob=date(1955, 10, 12),
        mrn=mrn,
        phone="+18005551212",
    )
    treatment = Treatment(
        patient=patient,
        status="completed",
        automation_mode="inactive",
        clinical_objective="Monitor recovery",
        archived_at=effective_archived_at,
    )
    session.add(treatment)
    await session.flush()
    message = ConversationMessage(
        treatment_id=treatment.id,
        direction="inbound",
        sender_type="patient",
        channel="whatsapp",
        status="received",
        body="Patient text should not be copied into retention audit rows.",
    )
    session.add_all(
        [
            message,
            AuditLogEntry(
                event_type="treatment_archived",
                resource_type="treatment",
                resource_id=treatment.id,
                payload={"treatment_id": str(treatment.id)},
            ),
        ]
    )
    await session.flush()
    return treatment
