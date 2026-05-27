"""Internal maintenance endpoints."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models import AuditLogEntry, ConversationMessage, KnowledgeDocument, Patient, Treatment
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


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_knowledge_upload_files_removes_removed_upload_files_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
    test_app: FastAPI,
    tmp_path: Path,
) -> None:
    test_app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        knowledge_upload_dir=str(tmp_path),
    )
    owner_id = uuid4()
    removed_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/removed-protocol.pdf",
        title="Removed Protocol",
        mime="application/pdf",
        status="removed",
        uploaded_by=owner_id,
    )
    active_document = KnowledgeDocument(
        source_type="user_upload",
        source_uri="local://kb/active-protocol.pdf",
        title="Active Protocol",
        mime="application/pdf",
        status="ready",
        uploaded_by=owner_id,
    )
    db_session.add_all([removed_document, active_document])
    await db_session.flush()
    removed_path = tmp_path / f"{removed_document.id}.bin"
    active_path = tmp_path / f"{active_document.id}.bin"
    removed_path.write_bytes(b"removed clinical asset")
    active_path.write_bytes(b"active clinical asset")

    response = await app_client.post("/internal/cleanup/knowledge-upload-files")

    audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "kb_removed_upload_files_cleaned"
        )
    )

    assert response.status_code == 200
    assert response.json() == {
        "scanned_document_count": 1,
        "removed_file_count": 1,
        "missing_file_count": 0,
    }
    assert not removed_path.exists()
    assert active_path.exists()
    assert audit is not None
    assert audit.resource_type == "system"
    assert audit.payload == {
        "scanned_document_count": 1,
        "removed_file_count": 1,
        "missing_file_count": 0,
    }
    assert "Protocol" not in str(audit.payload)


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_operational_audit_logs_dry_run_does_not_delete_rows(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    old_operational = _audit_log(
        event_type="queue_task_retry_observed",
        created_at=datetime.now(UTC) - timedelta(days=90),
        payload={"retry_count": 2},
    )
    db_session.add(old_operational)
    await db_session.flush()

    response = await app_client.post(
        "/internal/cleanup/operational-audit-logs",
        json={"dry_run": True, "retention_days": 30},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "dry_run": True,
        "retention_days": 30,
        "eligible_audit_log_count": 1,
        "deleted_audit_log_count": 0,
    }
    assert await db_session.get(AuditLogEntry, old_operational.id) is not None


@pytest.mark.usefixtures("postgres_container")
async def test_cleanup_operational_audit_logs_deletes_only_old_operational_rows(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    old_operational = _audit_log(
        event_type="queue_dead_letter_received",
        created_at=datetime.now(UTC) - timedelta(days=90),
        payload={"queue_name": "internal"},
    )
    recent_operational = _audit_log(
        event_type="queue_task_retry_observed",
        created_at=datetime.now(UTC) - timedelta(days=5),
        payload={"retry_count": 1},
    )
    clinical_audit = _audit_log(
        event_type="treatment_created",
        created_at=datetime.now(UTC) - timedelta(days=90),
        resource_type="treatment",
        payload={"patient_text": "Should not be copied into cleanup audit."},
    )
    db_session.add_all([old_operational, recent_operational, clinical_audit])
    await db_session.flush()

    response = await app_client.post(
        "/internal/cleanup/operational-audit-logs",
        json={"dry_run": False, "retention_days": 30},
    )

    cleanup_audit = await db_session.scalar(
        select(AuditLogEntry).where(
            AuditLogEntry.event_type == "operational_audit_retention_cleanup"
        )
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "dry_run": False,
        "retention_days": 30,
        "eligible_audit_log_count": 1,
        "deleted_audit_log_count": 1,
    }
    assert await db_session.get(AuditLogEntry, old_operational.id) is None
    assert await db_session.get(AuditLogEntry, recent_operational.id) is not None
    assert await db_session.get(AuditLogEntry, clinical_audit.id) is not None
    assert cleanup_audit is not None
    assert cleanup_audit.payload == {
        "dry_run": False,
        "retention_days": 30,
        "eligible_audit_log_count": 1,
        "deleted_audit_log_count": 1,
    }
    assert "patient_text" not in str(cleanup_audit.payload)


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


def _audit_log(
    *,
    event_type: str,
    created_at: datetime,
    resource_type: str = "system",
    payload: dict[str, object] | None = None,
) -> AuditLogEntry:
    return AuditLogEntry(
        event_type=event_type,
        resource_type=resource_type,
        resource_id=UUID("00000000-0000-0000-0000-000000000000"),
        payload=payload or {},
        created_at=created_at,
    )
