"""Integration tests for SubmitMatchResultUseCase."""
from __future__ import annotations

from functools import partial

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import (
    LeagueNotFoundError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)


def _use_case(sf: async_sessionmaker) -> SubmitMatchResultUseCase:
    return SubmitMatchResultUseCase(partial(SqlAlchemySubmitMatchResultUnitOfWork, sf))


async def _create_league(sf: async_sessionmaker, title: str = "Test", token: str = "tok") -> League:
    async with sf() as s:
        league = League.create(title, None, token)
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()
    return league


async def test_creates_players_teams_and_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    result = await _use_case(session_factory).execute(
        SubmitMatchResultCommand(
            league_id=str(league.league_id),
            team1_nicknames=("alice", "bob"),
            team2_nicknames=("charlie", "diana"),
            team1_score="6",
            team2_score="3",
        )
    )

    assert result.match_id
    async with session_factory() as s:
        saved_league = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(saved_league.players) == 4
        assert len(saved_league.teams) == 2

        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)
        assert len(matches) == 1
        assert matches[0].set_score.team1_score == "6"
        assert matches[0].set_score.team2_score == "3"


async def test_reuses_existing_team_on_rematch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        team1_nicknames=("alice", "bob"),
        team2_nicknames=("charlie", "diana"),
        team1_score="6",
        team2_score="3",
    )

    await use_case.execute(cmd)
    await use_case.execute(cmd)

    async with session_factory() as s:
        saved = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(saved.players) == 4   # no duplicates
        assert len(saved.teams) == 2     # no duplicate teams

        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)
        assert len(matches) == 2


async def test_raises_for_unknown_league(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(LeagueNotFoundError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id="00000000-0000-0000-0000-000000000000",
                team1_nicknames=("alice", "bob"),
                team2_nicknames=("charlie", "diana"),
                team1_score="6",
                team2_score="3",
            )
        )


async def test_raises_for_same_player_within_team(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    with pytest.raises(SamePlayerWithinSingleTeamError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                team1_nicknames=("alice", "alice"),
                team2_nicknames=("charlie", "diana"),
                team1_score="6",
                team2_score="3",
            )
        )


async def test_raises_for_same_player_on_both_teams(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    with pytest.raises(SamePlayerOnBothTeamsError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                team1_nicknames=("alice", "bob"),
                team2_nicknames=("alice", "charlie"),
                team1_score="6",
                team2_score="3",
            )
        )


async def test_raises_when_player_already_in_another_team(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    use_case = _use_case(session_factory)

    # Register alice+bob as a team
    await use_case.execute(
        SubmitMatchResultCommand(
            league_id=str(league.league_id),
            team1_nicknames=("alice", "bob"),
            team2_nicknames=("charlie", "diana"),
            team1_score="6",
            team2_score="3",
        )
    )

    # Try to pair alice with eve in a different team
    with pytest.raises(TeamConflictError):
        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                team1_nicknames=("alice", "eve"),
                team2_nicknames=("frank", "grace"),
                team1_score="6",
                team2_score="3",
            )
        )
