"""Internal Pub/Sub scheduler tick endpoint."""

import base64
import json

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import internal as internal_api
from app.config import Settings, get_settings
from app.services import (
    data_retention,
    knowledge_storage,
    message_delivery,
    monitoring,
    task_runner,
)


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scheduler tick tests exercise worker dispatch, not treatment analysis."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_pubsub_tick_runs_due_monitoring(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_due_monitoring(
        session: AsyncSession,
    ) -> monitoring.DueMonitoringRunResult:
        assert session is not None
        return monitoring.DueMonitoringRunResult(
            processed_count=2,
            queued_count=3,
            skipped_count=1,
        )

    monkeypatch.setattr(monitoring, "run_due_monitoring", fake_run_due_monitoring)

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message({"tick_type": "due_monitoring"}),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tick_type": "due_monitoring",
        "result": {
            "processed_count": 2,
            "queued_count": 3,
            "skipped_count": 1,
        },
    }


@pytest.mark.usefixtures("postgres_container")
async def test_pubsub_tick_runs_message_delivery_from_attributes(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_message_delivery_once(
        session: AsyncSession,
    ) -> message_delivery.MessageDeliveryRunResult:
        assert session is not None
        return message_delivery.MessageDeliveryRunResult(
            processed_count=4,
            sent_count=3,
            failed_count=1,
        )

    monkeypatch.setattr(
        message_delivery,
        "run_message_delivery_once",
        fake_run_message_delivery_once,
    )

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message({}, attributes={"tick_type": "message_delivery"}),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tick_type": "message_delivery",
        "result": {
            "processed_count": 4,
            "sent_count": 3,
            "failed_count": 1,
        },
    }


@pytest.mark.usefixtures("postgres_container")
async def test_pubsub_tick_runs_closed_treatment_retention_dry_run(
    app_client: AsyncClient,
    test_app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None,
        data_retention_closed_treatment_days=45,
        data_retention_cleanup_dry_run=True,
    )
    test_app.dependency_overrides[get_settings] = lambda: settings

    async def fake_cleanup_closed_treatments(
        session: AsyncSession,
        *,
        retention_days: int,
        dry_run: bool = True,
        limit: int = 100,
    ) -> data_retention.ClosedTreatmentRetentionResult:
        assert session is not None
        assert retention_days == 45
        assert dry_run is True
        assert limit == 100
        return data_retention.ClosedTreatmentRetentionResult(
            dry_run=dry_run,
            retention_days=retention_days,
            eligible_treatment_count=2,
            deleted_treatment_count=0,
            deleted_patient_count=0,
            deleted_audit_log_count=0,
        )

    monkeypatch.setattr(
        data_retention,
        "cleanup_closed_treatments",
        fake_cleanup_closed_treatments,
    )

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message({"tick_type": "closed_treatment_retention"}),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tick_type": "closed_treatment_retention",
        "result": {
            "dry_run": True,
            "retention_days": 45,
            "eligible_treatment_count": 2,
            "deleted_treatment_count": 0,
            "deleted_patient_count": 0,
            "deleted_audit_log_count": 0,
        },
    }


@pytest.mark.usefixtures("postgres_container")
async def test_pubsub_tick_runs_knowledge_upload_file_cleanup(
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_cleanup_removed_upload_files(
        session: AsyncSession,
        storage: knowledge_storage.KnowledgeStorage,
        *,
        limit: int = 100,
    ) -> knowledge_storage.KnowledgeUploadCleanupResult:
        assert session is not None
        assert storage is not None
        assert limit == 100
        return knowledge_storage.KnowledgeUploadCleanupResult(
            scanned_document_count=3,
            removed_file_count=2,
            missing_file_count=1,
        )

    monkeypatch.setattr(
        internal_api,
        "cleanup_removed_upload_files",
        fake_cleanup_removed_upload_files,
    )

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message({"tick_type": "knowledge_upload_file_cleanup"}),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tick_type": "knowledge_upload_file_cleanup",
        "result": {
            "scanned_document_count": 3,
            "removed_file_count": 2,
            "missing_file_count": 1,
        },
    }


@pytest.mark.usefixtures("postgres_container")
async def test_pubsub_tick_rejects_unknown_tick_type(app_client: AsyncClient) -> None:
    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message({"tick_type": "unknown"}),
    )

    assert response.status_code == 400
    assert response.json() == {"detail": {"error": "unknown_scheduler_tick"}}


def _pubsub_message(
    payload: dict[str, str],
    *,
    attributes: dict[str, str] | None = None,
) -> dict[str, object]:
    data = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return {
        "message": {
            "data": data,
            "attributes": attributes or {},
            "messageId": "scheduler-tick-1",
        },
        "subscription": "projects/pharmaide/subscriptions/internal-scheduler",
    }
