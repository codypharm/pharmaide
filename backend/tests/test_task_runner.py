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


async def test_schedule_forwards_keyword_arguments() -> None:
    seen: list[str] = []

    async def record(*, value: str) -> None:
        await asyncio.sleep(0)
        seen.append(value)

    task_runner.schedule(record, value="configured")

    await task_runner.drain()

    assert seen == ["configured"]


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
