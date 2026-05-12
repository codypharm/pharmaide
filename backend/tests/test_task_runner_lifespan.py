"""Application lifespan drains scheduled background tasks."""

import asyncio

import pytest

from app.config import Settings
from app.main import create_app
from app.services import task_runner


@pytest.fixture(autouse=True)
async def drain_tasks() -> None:
    try:
        yield
    finally:
        await task_runner.drain()


async def test_app_shutdown_waits_for_scheduled_tasks() -> None:
    """FastAPI shutdown should not abandon in-flight background work."""
    app = create_app(Settings(_env_file=None))
    lifespan = app.router.lifespan_context(app)
    started = asyncio.Event()
    release = asyncio.Event()
    completed = False

    async def wait_for_release() -> None:
        nonlocal completed
        started.set()
        await release.wait()
        completed = True

    await lifespan.__aenter__()
    try:
        task_runner.schedule(wait_for_release)
        await started.wait()

        shutdown = asyncio.create_task(lifespan.__aexit__(None, None, None))
        await asyncio.sleep(0)
        assert not shutdown.done()

        release.set()
        await shutdown
    finally:
        if not release.is_set():
            release.set()

    assert completed is True
