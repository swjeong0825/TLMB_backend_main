"""Shared fixtures for all integration tests.

Integration tests bypass the HTTP layer and talk directly to the DB via
repositories and use cases.  They target the `tennis_league_integ` database
(configurable via the INTEG_DATABASE_URL env var) and do NOT touch the app's
production DATABASE_URL.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from functools import partial

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)

# ---------------------------------------------------------------------------
# Engine setup – NullPool prevents event-loop binding issues with pytest-asyncio
# ---------------------------------------------------------------------------

_INTEG_DB_URL = os.environ.get(
    "INTEG_DATABASE_URL",
    "postgresql+asyncpg://localhost/tennis_league_integ",
)

_engine = create_async_engine(_INTEG_DB_URL, echo=False, poolclass=NullPool)
_session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Core fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the integration session factory (for UoW / multi-session tests)."""
    return _session_factory


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a managed AsyncSession that auto-commits on success."""
    async with _session_factory() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tables after every test to keep tests isolated."""
    yield
    async with _engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE leagues CASCADE"))


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def persisted_league(session_factory: async_sessionmaker[AsyncSession]) -> League:
    """Create and commit a bare League (no players/teams yet)."""
    async with session_factory() as s:
        league = League.create("Fixture League", "Integration test league", "fixture-host-token")
        repo = SqlAlchemyLeagueRepository(s)
        await repo.save(league)
        await s.commit()
    return league


@pytest_asyncio.fixture
async def persisted_league_with_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> dict:
    """Create a League, submit one match, and return metadata for use in tests.

    Returns a dict with keys:
        league      – the re-queried League domain object (has players/teams populated)
        match_id    – str UUID of the created match
    """
    # Create league
    async with session_factory() as s:
        league = League.create("Fixture League", None, "fixture-host-token")
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()

    # Submit one match (creates players + teams automatically)
    use_case = SubmitMatchResultUseCase(
        partial(SqlAlchemySubmitMatchResultUnitOfWork, session_factory)
    )
    match_result = await use_case.execute(
        SubmitMatchResultCommand(
            league_id=str(league.league_id),
            team1_nicknames=("alice", "bob"),
            team2_nicknames=("charlie", "diana"),
            team1_score="6",
            team2_score="3",
        )
    )

    # Re-query the league so players/teams are populated
    async with session_factory() as s:
        fresh_league = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)

    return {"league": fresh_league, "match_id": match_result.match_id}
