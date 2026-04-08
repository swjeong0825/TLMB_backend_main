"""Integration tests for GetMatchHistoryUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.get_match_history_use_case import (
    GetMatchHistoryQuery,
    GetMatchHistoryUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import LeagueNotFoundError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


async def test_returns_empty_history_for_new_league(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create(
        "Empty", None, "tok", rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS
    )
    await repo.save(league)

    records = await GetMatchHistoryUseCase(repo, SqlAlchemyMatchRepository(session)).execute(
        GetMatchHistoryQuery(league_id=str(league.league_id))
    )

    assert records == []


async def test_returns_match_record_with_player_nicknames(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        records = await GetMatchHistoryUseCase(
            SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
        ).execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

    assert len(records) == 1
    record = records[0]
    assert record.match_id == match_id
    assert record.team1_score == "6"
    assert record.team2_score == "3"
    assert record.created_at is not None

    team1_players = {record.team1_player1_nickname, record.team1_player2_nickname}
    team2_players = {record.team2_player1_nickname, record.team2_player2_nickname}
    assert team1_players == {"alice", "bob"}
    assert team2_players == {"charlie", "diana"}


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    use_case = GetMatchHistoryUseCase(
        SqlAlchemyLeagueRepository(session),
        SqlAlchemyMatchRepository(session),
    )
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(GetMatchHistoryQuery(league_id="00000000-0000-0000-0000-000000000000"))
