"""Integration tests for GetLeagueRosterUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.get_league_roster_use_case import (
    GetLeagueRosterQuery,
    GetLeagueRosterUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import LeagueNotFoundError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


async def test_returns_empty_roster_for_new_league(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create(
        "Empty", None, "tok", rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS
    )
    await repo.save(league)

    roster = await GetLeagueRosterUseCase(repo).execute(
        GetLeagueRosterQuery(league_id=str(league.league_id))
    )

    assert roster.title == "Empty"
    assert roster.players == []
    assert roster.teams == []


async def test_returns_players_and_teams_after_match(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        roster = await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(s)).execute(
            GetLeagueRosterQuery(league_id=str(league.league_id))
        )

    assert roster.title == league.title
    nicknames = {p.nickname for p in roster.players}
    assert nicknames == {"alice", "bob", "charlie", "diana"}
    assert len(roster.teams) == 2

    # Verify team player names are populated
    for team in roster.teams:
        assert team.player1_nickname
        assert team.player2_nickname


async def test_players_sorted_alphabetically(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        roster = await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(s)).execute(
            GetLeagueRosterQuery(league_id=str(league.league_id))
        )

    player_nicknames = [p.nickname for p in roster.players]
    assert player_nicknames == sorted(player_nicknames)


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(session)).execute(
            GetLeagueRosterQuery(league_id="00000000-0000-0000-0000-000000000000")
        )
