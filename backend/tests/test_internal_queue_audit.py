"""Queue retry and dead-letter audit events for internal workers."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogEntry
from app.services import message_delivery, task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Queue audit tests should not schedule treatment analysis side effects."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_internal_worker_audits_cloud_tasks_retry_metadata(
    app_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_run_message_delivery_once(
        session: AsyncSession,
        **kwargs: object,
    ) -> message_delivery.MessageDeliveryRunResult:
        assert session is not None
        assert "provider" in kwargs
        return message_delivery.MessageDeliveryRunResult(
            processed_count=0,
            sent_count=0,
            failed_count=0,
        )

    monkeypatch.setattr(
        message_delivery,
        "run_message_delivery_once",
        fake_run_message_delivery_once,
    )

    response = await app_client.post(
        "/internal/message-delivery/run-once",
        headers={
            "X-CloudTasks-QueueName": "message-delivery",
            "X-CloudTasks-TaskName": "pa-task-123",
            "X-CloudTasks-TaskRetryCount": "2",
            "X-CloudTasks-TaskExecutionCount": "3",
        },
    )

    assert response.status_code == 200, response.text
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "queue_task_retry_observed")
    )
    assert audit is not None
    assert audit.resource_type == "queue_task"
    assert audit.payload == {
        "queue_name": "message-delivery",
        "task_name": "pa-task-123",
        "retry_count": 2,
        "execution_count": 3,
        "worker_path": "/internal/message-delivery/run-once",
    }


@pytest.mark.usefixtures("postgres_container")
async def test_dead_letter_endpoint_audits_metadata_only(
    app_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    response = await app_client.post(
        "/internal/queue/dead-letter",
        json={
            "source": "cloud_tasks",
            "queue_name": "analysis",
            "task_name": "pa-task-failed",
            "job_name": "analysis.run",
            "reason": "max_attempts_exhausted",
            "attempt_count": 5,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"recorded": True}
    audit = await db_session.scalar(
        select(AuditLogEntry).where(AuditLogEntry.event_type == "queue_dead_letter_received")
    )
    assert audit is not None
    assert audit.resource_type == "queue_task"
    assert audit.payload == {
        "source": "cloud_tasks",
        "queue_name": "analysis",
        "task_name": "pa-task-failed",
        "job_name": "analysis.run",
        "reason": "max_attempts_exhausted",
        "attempt_count": 5,
    }
