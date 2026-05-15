"""Internal maintenance endpoints."""

from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry
from app.services import dailymed_cache, task_runner


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
