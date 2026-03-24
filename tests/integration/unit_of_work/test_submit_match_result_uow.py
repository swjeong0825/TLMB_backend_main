"""Integration tests for SqlAlchemySubmitMatchResultUnitOfWork.

These tests verify the atomicity guarantee: league save and match save
are committed together, or rolled back together.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)


async def _create_league(sf: async_sessionmaker, token: str = "tok") -> League:
    async with sf() as s:
        league = League.create("UoW Test League", None, token)
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()
    return league


async def test_commit_persists_league_changes_and_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)

    async with SqlAlchemySubmitMatchResultUnitOfWork(session_factory) as uow:
        saved_league = await uow.league_repo.get_by_id_with_lock(league.league_id)
        _, team1 = saved_league.register_players_and_team("alice", "bob")
        _, team2 = saved_league.register_players_and_team("charlie", "diana")
        match = Match.create(league.league_id, team1.team_id, team2.team_id, SetScore("6", "3"))
        await uow.league_repo.save(saved_league)
        await uow.match_repo.save(match)
        await uow.commit()

    # Verify both league changes and match are visible in a fresh session
    async with session_factory() as s:
        refreshed = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(refreshed.players) == 4
        assert len(refreshed.teams) == 2

        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)
        assert len(matches) == 1
        assert str(matches[0].match_id.value) == str(match.match_id.value)


async def test_rollback_on_exception_leaves_db_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    league_id = league.league_id

    class _BoomError(Exception):
        pass

    with pytest.raises(_BoomError):
        async with SqlAlchemySubmitMatchResultUnitOfWork(session_factory) as uow:
            saved_league = await uow.league_repo.get_by_id_with_lock(league_id)
            saved_league.register_players_and_team("alice", "bob")
            await uow.league_repo.save(saved_league)
            raise _BoomError("forced rollback")

    # After rollback, no players should have been persisted
    async with session_factory() as s:
        refreshed = await SqlAlchemyLeagueRepository(s).get_by_id(league_id)
        assert len(refreshed.players) == 0
        assert len(refreshed.teams) == 0


async def test_league_repo_and_match_repo_share_the_same_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Both repos must operate on the same session to ensure atomicity."""
    async with SqlAlchemySubmitMatchResultUnitOfWork(session_factory) as uow:
        assert uow.league_repo._session is uow.match_repo._session


async def test_without_commit_changes_are_not_visible(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)

    # Enter UoW context but do NOT call commit()
    async with SqlAlchemySubmitMatchResultUnitOfWork(session_factory) as uow:
        saved_league = await uow.league_repo.get_by_id_with_lock(league.league_id)
        saved_league.register_players_and_team("alice", "bob")
        await uow.league_repo.save(saved_league)
        # ← no commit()

    async with session_factory() as s:
        refreshed = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(refreshed.players) == 0
