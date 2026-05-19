"""Service-to-service auth for internal worker routes."""

import base64
import json

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.services import internal_worker_auth, monitoring, task_runner


@pytest.fixture(autouse=True)
def disable_analysis_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth tests should not schedule treatment analysis side effects."""
    monkeypatch.setattr(task_runner, "schedule", lambda *args, **kwargs: None)


@pytest.mark.usefixtures("postgres_container")
async def test_internal_worker_auth_rejects_missing_bearer_token(
    test_app: FastAPI,
    app_client: AsyncClient,
) -> None:
    test_app.state.settings = Settings(
        _env_file=None,
        internal_worker_auth="oidc",
        internal_worker_audience="https://worker.test",
    )

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        json=_pubsub_message("due_monitoring"),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"error": "internal_worker_auth_required"}}


@pytest.mark.usefixtures("postgres_container")
async def test_internal_worker_auth_rejects_invalid_oidc_token(
    test_app: FastAPI,
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_app.state.settings = Settings(
        _env_file=None,
        internal_worker_auth="oidc",
        internal_worker_audience="https://worker.test",
    )

    def reject_token(token: str, audience: str) -> dict[str, object]:
        assert token == "bad-token"
        assert audience == "https://worker.test"
        raise internal_worker_auth.InternalWorkerAuthError("invalid token")

    monkeypatch.setattr(internal_worker_auth, "verify_internal_oidc_token", reject_token)

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        headers={"Authorization": "Bearer bad-token"},
        json=_pubsub_message("due_monitoring"),
    )

    assert response.status_code == 401
    assert response.json() == {"detail": {"error": "internal_worker_auth_invalid"}}


@pytest.mark.usefixtures("postgres_container")
async def test_internal_worker_auth_accepts_valid_oidc_token(
    test_app: FastAPI,
    app_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_app.state.settings = Settings(
        _env_file=None,
        internal_worker_auth="oidc",
        internal_worker_audience="https://worker.test",
    )

    def accept_token(token: str, audience: str) -> dict[str, object]:
        assert token == "good-token"
        assert audience == "https://worker.test"
        return {"email": "tasks-invoker@pharmaide.iam.gserviceaccount.com"}

    async def fake_run_due_monitoring(
        session: AsyncSession,
    ) -> monitoring.DueMonitoringRunResult:
        assert session is not None
        return monitoring.DueMonitoringRunResult(
            processed_count=1,
            queued_count=2,
            skipped_count=0,
        )

    monkeypatch.setattr(internal_worker_auth, "verify_internal_oidc_token", accept_token)
    monkeypatch.setattr(monitoring, "run_due_monitoring", fake_run_due_monitoring)

    response = await app_client.post(
        "/internal/scheduler/pubsub",
        headers={"Authorization": "Bearer good-token"},
        json=_pubsub_message("due_monitoring"),
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "tick_type": "due_monitoring",
        "result": {
            "processed_count": 1,
            "queued_count": 2,
            "skipped_count": 0,
        },
    }


def _pubsub_message(tick_type: str) -> dict[str, object]:
    data = base64.b64encode(json.dumps({"tick_type": tick_type}).encode("utf-8")).decode(
        "ascii"
    )
    return {
        "message": {
            "data": data,
            "attributes": {},
            "messageId": "scheduler-tick-1",
        },
        "subscription": "projects/pharmaide/subscriptions/internal-scheduler",
    }
