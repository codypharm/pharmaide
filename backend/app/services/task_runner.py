"""In-process background task runner.

Routes use this module when work should continue after the HTTP response
has returned. For Sprint 3 that means `asyncio.create_task`; in Sprint 5
this module is the transport seam where Cloud Tasks can replace the local
implementation while callers keep the same `schedule(coro_fn, *args)` shape.
"""

import asyncio
import hashlib
import json
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from app.config import Settings


class RateLimitExceeded(Exception):
    """Raised when one user already owns the configured number of live tasks."""

    def __init__(self, user_id: str) -> None:
        super().__init__(user_id)
        self.user_id = user_id


class TaskBackendUnavailable(RuntimeError):
    """Raised when a configured durable task backend is not ready to enqueue."""


@dataclass(frozen=True)
class CheckpointCleanupResult:
    deleted_count: int
    freed_mb: float


@dataclass(frozen=True)
class BackgroundJob:
    """Metadata-only description of background work for a future queue adapter."""

    name: str
    idempotency_key: str
    payload: Mapping[str, object]


class BackgroundJobScheduler(Protocol):
    """Minimal scheduler contract that a Cloud Tasks adapter can later satisfy."""

    def schedule[T](
        self,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> asyncio.Task[T]:
        """Schedule background work and return the local task handle when available."""
        ...

    def schedule_job[T](
        self,
        job: BackgroundJob,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> object:
        """Schedule named background work and return the local task handle."""
        ...

    async def drain(self) -> None:
        """Wait for locally tracked work to finish."""
        ...


class InProcessBackgroundJobScheduler:
    """Local scheduler used before production Cloud Tasks/Pub/Sub is wired."""

    def __init__(self) -> None:
        self._live_tasks: set[asyncio.Task[Any]] = set()
        self._user_tasks: dict[str, set[asyncio.Future[Any]]] = {}

    def schedule[T](
        self,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> asyncio.Task[T]:
        """Start a coroutine and keep a strong reference until completion."""
        if user_id is not None and max_concurrent_per_user is not None:
            user_tasks = self._user_tasks.setdefault(user_id, set())
            if len(user_tasks) >= max_concurrent_per_user:
                raise RateLimitExceeded(user_id)

        task: asyncio.Task[T] = asyncio.create_task(coro_fn(*args, **kwargs))
        self._live_tasks.add(task)
        task.add_done_callback(self._live_tasks.discard)
        if user_id is not None and max_concurrent_per_user is not None:
            user_tasks.add(task)
            task.add_done_callback(lambda done_task: self._forget_user_task(user_id, done_task))
        return task

    def schedule_job[T](
        self,
        job: BackgroundJob,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> asyncio.Task[T]:
        """Run named jobs locally while preserving production queue metadata."""
        del job
        return self.schedule(
            coro_fn,
            *args,
            user_id=user_id,
            max_concurrent_per_user=max_concurrent_per_user,
            **kwargs,
        )

    async def drain(self) -> None:
        """Wait for all scheduled tasks to finish.

        Shutdown should wait for in-flight clinical/audit work, but one failed
        task should not prevent the runner from waiting on the remaining tasks.
        """
        while self._live_tasks:
            await asyncio.gather(*self._live_tasks, return_exceptions=True)

    def _forget_user_task(self, user_id: str, task: asyncio.Future[Any]) -> None:
        tasks = self._user_tasks.get(user_id)
        if tasks is None:
            return
        tasks.discard(task)
        if not tasks:
            self._user_tasks.pop(user_id, None)


@dataclass(frozen=True)
class CloudTasksSchedulerConfig:
    """Deployment metadata needed by the future Cloud Tasks client."""

    queue_path: str
    base_url: str
    service_account_email: str
    oidc_audience: str


class CloudTasksBackgroundJobScheduler:
    """Durable scheduler that enqueues metadata-only HTTP worker tasks."""

    def __init__(self, config: CloudTasksSchedulerConfig, *, client: object | None = None) -> None:
        self.config = config
        self._client = client

    def schedule[T](
        self,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> asyncio.Task[T]:
        del coro_fn, args, user_id, max_concurrent_per_user, kwargs
        raise TaskBackendUnavailable(
            "Cloud Tasks backend only supports named jobs and is not wired yet."
        )

    def schedule_job[T](
        self,
        job: BackgroundJob,
        coro_fn: Callable[..., Coroutine[Any, Any, T]],
        *args: object,
        user_id: str | None = None,
        max_concurrent_per_user: int | None = None,
        **kwargs: object,
    ) -> object:
        del coro_fn, args, user_id, max_concurrent_per_user, kwargs
        return self._create_task(job)

    async def drain(self) -> None:
        """Cloud Tasks owns durable work; there are no local tasks to drain."""


    def _create_task(self, job: BackgroundJob) -> object:
        client = self._client or _build_cloud_tasks_client()
        tasks_v2 = _cloud_tasks_module()
        target = _cloud_task_target(self.config.base_url, job)
        task = tasks_v2.Task(
            name=f"{self.config.queue_path}/tasks/{_cloud_task_id(job.idempotency_key)}",
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=target.url,
                headers={"Content-Type": "application/json"},
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=self.config.service_account_email,
                    audience=self.config.oidc_audience,
                ),
                body=json.dumps(target.body, separators=(",", ":")).encode("utf-8"),
            ),
        )
        return client.create_task(
            tasks_v2.CreateTaskRequest(parent=self.config.queue_path, task=task)
        )


@dataclass(frozen=True)
class CloudTaskTarget:
    url: str
    body: Mapping[str, object]


def build_scheduler(
    settings: Settings,
    *,
    cloud_tasks_client: object | None = None,
) -> BackgroundJobScheduler:
    """Build the background scheduler selected by environment settings."""
    if settings.task_backend == "in_process":
        return InProcessBackgroundJobScheduler()

    return CloudTasksBackgroundJobScheduler(
        CloudTasksSchedulerConfig(
            queue_path=settings.cloud_tasks_queue_path or "",
            base_url=settings.cloud_tasks_base_url or "",
            service_account_email=settings.cloud_tasks_service_account_email or "",
            oidc_audience=settings.cloud_tasks_oidc_audience or "",
        ),
        client=cloud_tasks_client,
    )


def _cloud_task_target(base_url: str, job: BackgroundJob) -> CloudTaskTarget:
    base = base_url.rstrip("/")
    if job.name == "analysis.run":
        analysis_id = _required_payload_value(job, "analysis_id")
        return CloudTaskTarget(
            url=f"{base}/internal/analyses/{analysis_id}/run",
            body=_filtered_payload(job, {"kb_scope_id", "timeout_seconds"}),
        )

    if job.name == "kb.ingest":
        document_id = _required_payload_value(job, "document_id")
        return CloudTaskTarget(
            url=f"{base}/internal/knowledge/documents/{document_id}/ingest",
            body={},
        )

    raise TaskBackendUnavailable(f"Cloud Tasks job is not mapped: {job.name}")


def _required_payload_value(job: BackgroundJob, key: str) -> object:
    value = job.payload.get(key)
    if value is None:
        raise TaskBackendUnavailable(f"Cloud Tasks job {job.name} missing payload field: {key}")
    return value


def _filtered_payload(job: BackgroundJob, allowed_keys: set[str]) -> dict[str, object]:
    return {
        key: value
        for key, value in job.payload.items()
        if key in allowed_keys and value is not None
    }


def _cloud_task_id(idempotency_key: str) -> str:
    """Keep task ids deterministic without leaking raw resource identifiers."""
    return f"pa-{hashlib.sha256(idempotency_key.encode('utf-8')).hexdigest()[:40]}"


def _build_cloud_tasks_client() -> object:
    return _cloud_tasks_module().CloudTasksClient()


def _cloud_tasks_module() -> Any:
    try:
        from google.cloud import tasks_v2
    except ImportError as exc:
        raise TaskBackendUnavailable(
            "google-cloud-tasks is required when PHARMAIDE_TASK_BACKEND=cloud_tasks"
        ) from exc
    return cast(Any, tasks_v2)


_scheduler: BackgroundJobScheduler = InProcessBackgroundJobScheduler()


def schedule[T](
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: object,
    user_id: str | None = None,
    max_concurrent_per_user: int | None = None,
    **kwargs: object,
) -> asyncio.Task[T]:
    """Schedule background work through the configured local scheduler."""
    return _scheduler.schedule(
        coro_fn,
        *args,
        user_id=user_id,
        max_concurrent_per_user=max_concurrent_per_user,
        **kwargs,
    )


def schedule_job[T](
    job: BackgroundJob,
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: object,
    user_id: str | None = None,
    max_concurrent_per_user: int | None = None,
    **kwargs: object,
) -> asyncio.Task[T]:
    """Schedule a named job through the local runner.

    The metadata is the production queue contract. Local execution still flows
    through `schedule(...)` so existing tests and dev hooks that monkeypatch the
    old seam keep suppressing in-process work.
    """
    del job
    return schedule(
        coro_fn,
        *args,
        user_id=user_id,
        max_concurrent_per_user=max_concurrent_per_user,
        **kwargs,
    )


async def drain() -> None:
    """Wait for all scheduled local tasks to finish."""
    await _scheduler.drain()


def cleanup_checkpoints(
    checkpoint_db_path: str,
    *,
    max_age_days: int = 7,
) -> CheckpointCleanupResult:
    """Delete stale SQLite checkpoint files for the configured graph store."""
    checkpoint = Path(checkpoint_db_path)
    cutoff = time.time() - (max_age_days * 86_400)
    deleted_count = 0
    freed_bytes = 0

    for path in _checkpoint_file_candidates(checkpoint):
        if not path.is_file() or path.stat().st_mtime >= cutoff:
            continue
        size = path.stat().st_size
        path.unlink()
        deleted_count += 1
        freed_bytes += size

    return CheckpointCleanupResult(
        deleted_count=deleted_count,
        freed_mb=round(freed_bytes / 1_000_000, 3),
    )


def _checkpoint_file_candidates(checkpoint: Path) -> tuple[Path, Path, Path]:
    return (
        checkpoint,
        checkpoint.with_name(f"{checkpoint.name}-wal"),
        checkpoint.with_name(f"{checkpoint.name}-shm"),
    )
