from __future__ import annotations

import os

# Must be set before any app module is imported – database.py reads DATABASE_URL
# at module-load time to create the engine.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://@localhost:5432/tennis_league_e2e",
)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Patch the app's database singletons to use NullPool BEFORE the app is
# imported.  NullPool creates a fresh asyncpg connection for every
# `async with engine.begin()` call, which means the connection is always
# bound to the *current* event loop.  This avoids the
# "Future attached to a different loop" / "another operation is in progress"
# errors that arise when pytest-asyncio spins up a new loop per test while
# the app's connection pool holds connections from a previous loop.
# ---------------------------------------------------------------------------
_TEST_DB_URL = os.environ["DATABASE_URL"]

import app.infrastructure.config.database as _db_module  # noqa: E402

_test_engine = create_async_engine(_TEST_DB_URL, echo=False, poolclass=NullPool)
_test_session_factory = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)

_db_module.engine = _test_engine
_db_module.AsyncSessionFactory = _test_session_factory

# app.dependencies imports AsyncSessionFactory from the database module.
# Importing it here (after the patch above) ensures it picks up the test factory.
import app.dependencies as _deps_module  # noqa: E402

_deps_module.AsyncSessionFactory = _test_session_factory

# Only now import the full app so all sub-modules see the patched singletons.
from app.main import app  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tables after each test to keep tests isolated."""
    yield
    async with _test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE leagues CASCADE"))
