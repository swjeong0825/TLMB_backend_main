"""Integration tests for SqlAlchemySubmitSinglesMatchResultUnitOfWork."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.singles_match_repository import (
    SqlAlchemySinglesMatchRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_singles_match_result_uow import (
    SqlAlchemySubmitSinglesMatchResultUnitOfWork,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS


async def _create_league(sf: async_sessionmaker, token: str = "tok") -> League:
    async with sf() as s:
        league = League.create(
            "Singles UoW Test League",
            None,
            token,
            host_email="host@example.com",
            rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
        )
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()
    return league


async def test_commit_persists_league_changes_and_singles_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)

    async with SqlAlchemySubmitSinglesMatchResultUnitOfWork(session_factory) as uow:
        saved_league = await uow.league_repo.get_by_id_with_lock(league.league_id)
        alice = saved_league.register_single_player("alice")
        bob = saved_league.register_single_player("bob")
        match = SinglesMatch.create(
            league.league_id,
            alice.player_id,
            bob.player_id,
            SetScore("6", "3"),
        )
        await uow.league_repo.save(saved_league)
        await uow.singles_match_repo.save(match)
        await uow.commit()

    async with session_factory() as s:
        refreshed = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(refreshed.players) == 2
        assert len(refreshed.pairs) == 0

        matches = await SqlAlchemySinglesMatchRepository(s).get_all_by_league(
            league.league_id
        )
        assert len(matches) == 1
        assert matches[0].match_id == match.match_id


async def test_rollback_on_exception_leaves_db_unchanged(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)

    class _BoomError(Exception):
        pass

    with pytest.raises(_BoomError):
        async with SqlAlchemySubmitSinglesMatchResultUnitOfWork(session_factory) as uow:
            saved_league = await uow.league_repo.get_by_id_with_lock(league.league_id)
            alice = saved_league.register_single_player("alice")
            bob = saved_league.register_single_player("bob")
            match = SinglesMatch.create(
                league.league_id,
                alice.player_id,
                bob.player_id,
                SetScore("6", "3"),
            )
            await uow.league_repo.save(saved_league)
            await uow.singles_match_repo.save(match)
            raise _BoomError("forced rollback")

    async with session_factory() as s:
        refreshed = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        matches = await SqlAlchemySinglesMatchRepository(s).get_all_by_league(
            league.league_id
        )
        assert len(refreshed.players) == 0
        assert matches == []


async def test_repositories_share_the_same_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with SqlAlchemySubmitSinglesMatchResultUnitOfWork(session_factory) as uow:
        assert uow.league_repo._session is uow.singles_match_repo._session

