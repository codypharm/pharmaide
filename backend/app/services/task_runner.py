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


def schedule[T](coro_fn: Callable[..., Coroutine[Any, Any, T]], *args: object) -> asyncio.Task[T]:
    """Start a coroutine in the background and keep it alive until completion.

    The module-level set is intentional: the event loop only keeps weak task
    references, so a fire-and-forget task can otherwise be garbage-collected
    before it finishes.
    """
    task: asyncio.Task[T] = asyncio.create_task(coro_fn(*args))
    _live_tasks.add(task)
    task.add_done_callback(_live_tasks.discard)
    return task


async def drain() -> None:
    """Wait for all scheduled tasks to finish.

    Shutdown should wait for in-flight clinical/audit work, but one failed
    task should not prevent the runner from waiting on the remaining tasks.
    """
    while _live_tasks:
        await asyncio.gather(*_live_tasks, return_exceptions=True)
