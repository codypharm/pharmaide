"""Async SQLAlchemy engine + session factory.

Module-level engine and sessionmaker bound to the running app's settings.
Tests construct their own engine/factory pointed at the testcontainers
DB rather than the dev one — so the engine module exposes both factory
functions and a default instance.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def make_engine(database_url: str) -> AsyncEngine:
    # pool_pre_ping protects against stale connections after the DB
    # restarts or a network blip — common with managed Postgres.
    return create_async_engine(database_url, echo=False, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False so attributes stay accessible after commit
    # without forcing a re-fetch — the standard async-session pattern.
    return async_sessionmaker(engine, expire_on_commit=False)


# Default instances bound to the running app's settings. Tests never
# import these — they build their own pointed at the test container.
engine = make_engine(get_settings().database_url)
session_factory = make_session_factory(engine)
