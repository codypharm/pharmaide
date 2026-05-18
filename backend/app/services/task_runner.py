"""In-process background task runner.

Routes use this module when work should continue after the HTTP response
has returned. For Sprint 3 that means `asyncio.create_task`; in Sprint 5
this module is the transport seam where Cloud Tasks can replace the local
implementation while callers keep the same `schedule(coro_fn, *args)` shape.
"""

import asyncio
import time
from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class RateLimitExceeded(Exception):
    """Raised when one user already owns the configured number of live tasks."""

    def __init__(self, user_id: str) -> None:
        super().__init__(user_id)
        self.user_id = user_id


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
    ) -> asyncio.Task[T]:
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
