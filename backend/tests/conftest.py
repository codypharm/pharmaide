"""Shared pytest fixtures for the backend.

Lifecycle:
- postgres_container: session-scoped, spins one Postgres container, applies
  migrations once. ~5-10s first run; cached image after that.
- db_engine: session-scoped async engine bound to the container.
- db_session: function-scoped AsyncSession wrapped in a transaction that
  rolls back at teardown — every test sees a clean DB without dropping
  and recreating tables.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from testcontainers.postgres import PostgresContainer

from alembic import command
from app.config import Settings
from app.db.engine import get_session
from app.main import create_app

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _async_url(sync_url: str) -> str:
    # testcontainers returns a sync psycopg URL; SQLAlchemy async needs +asyncpg.
    return sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
        "postgresql://", "postgresql+asyncpg://"
    )


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[PostgresContainer]:
    container = PostgresContainer("postgres:17-alpine", username="pharmaide", password="pharmaide")
    container.start()
    try:
        async_url = _async_url(container.get_connection_url())
        cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
        cfg.set_main_option("sqlalchemy.url", async_url)
        cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
        command.upgrade(cfg, "head")
        yield container
    finally:
        container.stop()


@pytest.fixture(scope="session")
async def db_engine(postgres_container: PostgresContainer) -> AsyncIterator[object]:
    engine = create_async_engine(_async_url(postgres_container.get_connection_url()))
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: object) -> AsyncIterator[AsyncSession]:
    """Each test gets a fresh transaction that rolls back at teardown.

    Uses a connection-scoped session (not the standard sessionmaker pattern)
    so the explicit transaction wraps the entire test, including any
    intermediate flushes inside service code.
    """
    from sqlalchemy.ext.asyncio import AsyncEngine

    assert isinstance(db_engine, AsyncEngine)
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            if transaction.is_active:
                await transaction.rollback()


@pytest.fixture
def test_app(db_session: AsyncSession) -> FastAPI:
    """FastAPI app with get_session overridden to yield the test's db_session.

    Routes called via this app share the same transaction as the test,
    so the test can read back what the route inserted (and the rollback
    at teardown unwinds everything).
    """
    settings = Settings(_env_file=None, debug_routes_enabled=False, log_mode="json")
    app = create_app(settings)

    async def _override() -> AsyncIterator[AsyncSession]:
        # Use a savepoint so service-level flushes can be rolled back on
        # error without breaking the outer test transaction.
        async with db_session.begin_nested():
            yield db_session

    app.dependency_overrides[get_session] = _override
    return app


@pytest.fixture
async def app_client(test_app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
