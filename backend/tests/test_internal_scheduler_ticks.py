"""Internal Pub/Sub scheduler tick endpoint."""

import base64
import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import message_delivery, monitoring, task_runner


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
