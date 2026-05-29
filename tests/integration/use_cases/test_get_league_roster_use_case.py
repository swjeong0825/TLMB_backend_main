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
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS


async def test_returns_empty_roster_for_new_league(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create(
        "Empty",
        None,
        "tok",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
    )
    await repo.save(league)

    roster = await GetLeagueRosterUseCase(repo).execute(
        GetLeagueRosterQuery(league_id=str(league.league_id))
    )

    assert roster.title == "Empty"
    assert roster.players == []
    assert roster.pairs == []
    assert roster.rules == league.rules.to_dict()
    assert roster.latest_match_date is None


async def test_returns_players_and_pairs_after_match(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        roster = await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(s)).execute(
            GetLeagueRosterQuery(league_id=str(league.league_id))
        )

    assert roster.title == league.title
    assert roster.latest_match_date == league.latest_match_date
    nicknames = {p.nickname for p in roster.players}
    assert nicknames == {"alice", "bob", "charlie", "diana"}
    assert len(roster.pairs) == 2

    # Verify pair player names are populated
    for pair in roster.pairs:
        assert pair.player1_nickname
        assert pair.player2_nickname


async def test_players_sorted_alphabetically(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        roster = await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(s)).execute(
            GetLeagueRosterQuery(league_id=str(league.league_id))
        )

    player_nicknames = [p.nickname for p in roster.players]
    assert player_nicknames == sorted(player_nicknames)


async def test_player_rating_is_returned(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create(
        "Rated",
        None,
        "tok-rated",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
    )
    league.add_players(["alex"], ratings=[3.5])
    await repo.save(league)

    roster = await GetLeagueRosterUseCase(repo).execute(
        GetLeagueRosterQuery(league_id=str(league.league_id))
    )

    assert roster.players[0].nickname == "alex"
    assert roster.players[0].rating == 3.5


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await GetLeagueRosterUseCase(SqlAlchemyLeagueRepository(session)).execute(
            GetLeagueRosterQuery(league_id="00000000-0000-0000-0000-000000000000")
        )
