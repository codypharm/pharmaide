"""In-process task runner."""

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings
from app.services import task_runner


class FakeCloudTasksClient:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def create_task(self, request: object) -> object:
        self.requests.append(request)
        return {"name": "created-task"}


@pytest.fixture(autouse=True)
async def drain_tasks() -> AsyncIterator[None]:
    try:
        yield
    finally:
        await task_runner.drain()


async def test_schedule_runs_multiple_coroutines() -> None:
    seen: list[int] = []

    async def record(value: int) -> None:
        await asyncio.sleep(0)
        seen.append(value)

    for value in range(3):
        task_runner.schedule(record, value)

    await task_runner.drain()

    assert sorted(seen) == [0, 1, 2]


async def test_schedule_forwards_keyword_arguments() -> None:
    seen: list[str] = []

    async def record(*, value: str) -> None:
        await asyncio.sleep(0)
        seen.append(value)

    task_runner.schedule(record, value="configured")

    await task_runner.drain()

    assert seen == ["configured"]


async def test_in_process_scheduler_matches_background_job_interface() -> None:
    seen: list[str] = []
    scheduler: task_runner.BackgroundJobScheduler = task_runner.InProcessBackgroundJobScheduler()

    async def record(value: str) -> None:
        await asyncio.sleep(0)
        seen.append(value)

    scheduler.schedule(record, "named-job")

    await scheduler.drain()

    assert seen == ["named-job"]


async def test_schedule_job_runs_coroutine_with_metadata() -> None:
    seen: list[str] = []
    job = task_runner.BackgroundJob(
        name="analysis.run",
        idempotency_key="analysis:analysis-1",
        payload={"analysis_id": "analysis-1"},
    )

    async def record(value: str) -> None:
        await asyncio.sleep(0)
        seen.append(value)

    task_runner.schedule_job(job, record, "scheduled")

    await task_runner.drain()

    assert seen == ["scheduled"]


def test_build_scheduler_defaults_to_in_process() -> None:
    settings = Settings(_env_file=None)

    scheduler = task_runner.build_scheduler(settings)

    assert isinstance(scheduler, task_runner.InProcessBackgroundJobScheduler)


async def test_cloud_tasks_scheduler_enqueues_analysis_job() -> None:
    settings = Settings(
        _env_file=None,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide/locations/europe-west2/queues/default",
        cloud_tasks_base_url="https://worker.test/",
        cloud_tasks_service_account_email="tasks-invoker@pharmaide.iam.gserviceaccount.com",
        cloud_tasks_oidc_audience="https://worker.test",
    )
    fake_client = FakeCloudTasksClient()
    scheduler = task_runner.build_scheduler(settings, cloud_tasks_client=fake_client)
    job = task_runner.BackgroundJob(
        name="analysis.run",
        idempotency_key="analysis:analysis-1",
        payload={
            "analysis_id": "00000000-0000-4000-8000-000000000001",
            "kb_scope_id": "00000000-0000-4000-8000-000000000002",
            "timeout_seconds": 45,
        },
    )

    result = scheduler.schedule_job(job, _unexpected_coroutine)

    assert result == {"name": "created-task"}
    assert len(fake_client.requests) == 1
    request = fake_client.requests[0]
    assert request.parent == "projects/pharmaide/locations/europe-west2/queues/default"
    assert request.task.name.startswith(
        "projects/pharmaide/locations/europe-west2/queues/default/tasks/"
    )
    assert request.task.http_request.url == (
        "https://worker.test/internal/analyses/00000000-0000-4000-8000-000000000001/run"
    )
    assert request.task.http_request.headers["Content-Type"] == "application/json"
    assert json.loads(request.task.http_request.body.decode()) == {
        "kb_scope_id": "00000000-0000-4000-8000-000000000002",
        "timeout_seconds": 45,
    }
    assert (
        request.task.http_request.oidc_token.service_account_email
        == "tasks-invoker@pharmaide.iam.gserviceaccount.com"
    )
    assert request.task.http_request.oidc_token.audience == "https://worker.test"


async def test_configured_cloud_tasks_scheduler_receives_module_level_schedule_job() -> None:
    settings = Settings(
        _env_file=None,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide/locations/europe-west2/queues/default",
        cloud_tasks_base_url="https://worker.test",
        cloud_tasks_service_account_email="tasks-invoker@pharmaide.iam.gserviceaccount.com",
        cloud_tasks_oidc_audience="https://worker.test",
    )
    fake_client = FakeCloudTasksClient()
    scheduler = task_runner.build_scheduler(settings, cloud_tasks_client=fake_client)
    job = task_runner.BackgroundJob(
        name="analysis.run",
        idempotency_key="analysis:analysis-1",
        payload={"analysis_id": "00000000-0000-4000-8000-000000000001"},
    )

    task_runner.configure_scheduler(scheduler)
    try:
        task_runner.schedule_job(job, _unexpected_coroutine)
    finally:
        task_runner.configure_scheduler(task_runner.InProcessBackgroundJobScheduler())

    assert len(fake_client.requests) == 1
    assert fake_client.requests[0].task.http_request.url == (
        "https://worker.test/internal/analyses/00000000-0000-4000-8000-000000000001/run"
    )


async def test_cloud_tasks_scheduler_maps_knowledge_ingestion_job() -> None:
    settings = Settings(
        _env_file=None,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide/locations/europe-west2/queues/default",
        cloud_tasks_base_url="https://worker.test",
        cloud_tasks_service_account_email="tasks-invoker@pharmaide.iam.gserviceaccount.com",
        cloud_tasks_oidc_audience="https://worker.test",
    )
    fake_client = FakeCloudTasksClient()
    scheduler = task_runner.build_scheduler(settings, cloud_tasks_client=fake_client)
    job = task_runner.BackgroundJob(
        name="kb.ingest",
        idempotency_key="kb-ingest:document-1",
        payload={"document_id": "00000000-0000-4000-8000-000000000003"},
    )

    scheduler.schedule_job(job, _unexpected_coroutine)

    request = fake_client.requests[0]
    assert request.task.http_request.url == (
        "https://worker.test/internal/knowledge/documents/"
        "00000000-0000-4000-8000-000000000003/ingest"
    )
    assert json.loads(request.task.http_request.body.decode()) == {}


async def test_cloud_tasks_scheduler_maps_buffered_patient_turn_with_delay() -> None:
    settings = Settings(
        _env_file=None,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide/locations/europe-west2/queues/default",
        cloud_tasks_base_url="https://worker.test",
        cloud_tasks_service_account_email="tasks-invoker@pharmaide.iam.gserviceaccount.com",
        cloud_tasks_oidc_audience="https://worker.test",
    )
    fake_client = FakeCloudTasksClient()
    scheduler = task_runner.build_scheduler(settings, cloud_tasks_client=fake_client)
    job = task_runner.BackgroundJob(
        name="patient-turn.process",
        idempotency_key="patient-turn:00000000-0000-4000-8000-000000000004:12345",
        payload={
            "treatment_id": "00000000-0000-4000-8000-000000000004",
            "schedule_delay_seconds": 5,
        },
    )
    before = int(time.time())

    scheduler.schedule_job(job, _unexpected_coroutine)

    request = fake_client.requests[0]
    assert request.task.http_request.url == (
        "https://worker.test/internal/treatments/"
        "00000000-0000-4000-8000-000000000004/process-buffered-patient-turn"
    )
    assert json.loads(request.task.http_request.body.decode()) == {}
    schedule_timestamp = int(request.task.schedule_time.timestamp())
    assert before + 5 <= schedule_timestamp <= before + 10


async def test_cloud_tasks_scheduler_rejects_unknown_job_name() -> None:
    settings = Settings(
        _env_file=None,
        task_backend="cloud_tasks",
        cloud_tasks_queue_path="projects/pharmaide/locations/europe-west2/queues/default",
        cloud_tasks_base_url="https://worker.test",
        cloud_tasks_service_account_email="tasks-invoker@pharmaide.iam.gserviceaccount.com",
        cloud_tasks_oidc_audience="https://worker.test",
    )
    scheduler = task_runner.build_scheduler(settings, cloud_tasks_client=FakeCloudTasksClient())
    job = task_runner.BackgroundJob(
        name="unknown.job",
        idempotency_key="unknown:1",
        payload={},
    )

    with pytest.raises(task_runner.TaskBackendUnavailable, match=r"unknown\.job"):
        scheduler.schedule_job(job, _unexpected_coroutine)


async def _unexpected_coroutine() -> None:
    raise AssertionError("Cloud Tasks scheduling must not run work in-process.")


async def test_drain_waits_for_in_flight_tasks() -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    completed = False

    async def wait_for_release() -> None:
        nonlocal completed
        started.set()
        await release.wait()
        completed = True

    task_runner.schedule(wait_for_release)
    await started.wait()

    drain_task = asyncio.create_task(task_runner.drain())
    await asyncio.sleep(0)
    assert not drain_task.done()

    release.set()
    await drain_task

    assert completed is True


async def test_schedule_rejects_fourth_task_for_same_user() -> None:
    """One pharmacist should not be able to flood the local analysis runner."""
    release = asyncio.Event()

    async def wait_for_release() -> None:
        await release.wait()

    try:
        for _ in range(3):
            task_runner.schedule(
                wait_for_release,
                user_id="pharmacist-1",
                max_concurrent_per_user=3,
            )

        with pytest.raises(task_runner.RateLimitExceeded):
            task_runner.schedule(
                wait_for_release,
                user_id="pharmacist-1",
                max_concurrent_per_user=3,
            )
    finally:
        release.set()


async def test_schedule_counts_different_users_separately() -> None:
    release = asyncio.Event()

    async def wait_for_release() -> None:
        await release.wait()

    try:
        for _ in range(3):
            task_runner.schedule(
                wait_for_release,
                user_id="pharmacist-1",
                max_concurrent_per_user=3,
            )

        task = task_runner.schedule(
            wait_for_release,
            user_id="pharmacist-2",
            max_concurrent_per_user=3,
        )
        assert not task.done()
    finally:
        release.set()


def test_cleanup_checkpoints_deletes_only_stale_checkpoint_files(tmp_path: Path) -> None:
    checkpoint = tmp_path / "analysis.db"
    stale_checkpoint = checkpoint
    stale_wal = tmp_path / "analysis.db-wal"
    fresh_shm = tmp_path / "analysis.db-shm"
    unrelated = tmp_path / "other.db"

    for path in (stale_checkpoint, stale_wal, fresh_shm, unrelated):
        path.write_bytes(b"x" * 1024)

    old = (datetime.now(UTC) - timedelta(days=8)).timestamp()
    fresh = datetime.now(UTC).timestamp()
    for path in (stale_checkpoint, stale_wal, unrelated):
        path.touch()
        os.utime(path, (old, old))

    os.utime(fresh_shm, (fresh, fresh))

    result = task_runner.cleanup_checkpoints(str(checkpoint), max_age_days=7)

    assert result.deleted_count == 2
    assert result.freed_mb > 0
    assert not stale_checkpoint.exists()
    assert not stale_wal.exists()
    assert fresh_shm.exists()
    assert unrelated.exists()
