"""Application lifespan drains scheduled background tasks."""

import asyncio
from collections.abc import AsyncIterator

import pytest

from app.config import Settings
from app.main import create_app
from app.services import task_runner


@pytest.fixture(autouse=True)
async def drain_tasks() -> AsyncIterator[None]:
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


def test_create_app_configures_task_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    """The app factory is the production seam that applies env-selected workers."""
    built_with: list[Settings] = []

    class FakeScheduler:
        async def drain(self) -> None:
            return None

    def build_scheduler(settings: Settings) -> FakeScheduler:
        built_with.append(settings)
        return FakeScheduler()

    configured: list[FakeScheduler] = []

    monkeypatch.setattr(task_runner, "build_scheduler", build_scheduler)
    monkeypatch.setattr(task_runner, "configure_scheduler", configured.append)
    settings = Settings(_env_file=None)

    create_app(settings)

    assert built_with == [settings]
    assert len(configured) == 1
