"""In-process background task runner.

Routes use this module when work should continue after the HTTP response
has returned. For Sprint 3 that means `asyncio.create_task`; in Sprint 5
this module is the transport seam where Cloud Tasks can replace the local
implementation while callers keep the same `schedule(coro_fn, *args)` shape.
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

_live_tasks: set[asyncio.Task[Any]] = set()
_user_tasks: dict[str, set[asyncio.Future[Any]]] = {}


class RateLimitExceeded(Exception):
    """Raised when one user already owns the configured number of live tasks."""

    def __init__(self, user_id: str) -> None:
        super().__init__(user_id)
        self.user_id = user_id


def _forget_user_task(user_id: str, task: asyncio.Future[Any]) -> None:
    tasks = _user_tasks.get(user_id)
    if tasks is None:
        return
    tasks.discard(task)
    if not tasks:
        _user_tasks.pop(user_id, None)


def schedule[T](
    coro_fn: Callable[..., Coroutine[Any, Any, T]],
    *args: object,
    user_id: str | None = None,
    max_concurrent_per_user: int | None = None,
) -> asyncio.Task[T]:
    """Start a coroutine in the background and keep it alive until completion.

    The module-level set is intentional: the event loop only keeps weak task
    references, so a fire-and-forget task can otherwise be garbage-collected
    before it finishes.
    """
    if user_id is not None and max_concurrent_per_user is not None:
        user_tasks = _user_tasks.setdefault(user_id, set())
        if len(user_tasks) >= max_concurrent_per_user:
            raise RateLimitExceeded(user_id)

    task: asyncio.Task[T] = asyncio.create_task(coro_fn(*args))
    _live_tasks.add(task)
    task.add_done_callback(_live_tasks.discard)
    if user_id is not None and max_concurrent_per_user is not None:
        user_tasks.add(task)
        task.add_done_callback(lambda done_task: _forget_user_task(user_id, done_task))
    return task


async def drain() -> None:
    """Wait for all scheduled tasks to finish.

    Shutdown should wait for in-flight clinical/audit work, but one failed
    task should not prevent the runner from waiting on the remaining tasks.
    """
    while _live_tasks:
        await asyncio.gather(*_live_tasks, return_exceptions=True)
