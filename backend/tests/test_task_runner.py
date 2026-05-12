"""In-process task runner."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.services import task_runner


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
