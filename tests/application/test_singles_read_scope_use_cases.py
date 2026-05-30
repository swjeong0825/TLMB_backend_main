from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

from app.application.use_cases.get_match_history_use_case import (
    GetMatchHistoryQuery,
    GetMatchHistoryUseCase,
)
from app.application.use_cases.get_standings_use_case import (
    GetStandingsQuery,
    GetStandingsUseCase,
)
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from tests.application.conftest import make_league, make_match


def _singles_match(league, player1_name: str, player2_name: str) -> SinglesMatch:
    player1 = next(p for p in league.players if p.nickname.value == player1_name)
    player2 = next(p for p in league.players if p.nickname.value == player2_name)
    return SinglesMatch.create(
        league.league_id,
        player1.player_id,
        player2.player_id,
        SetScore("6", "1"),
    )


async def test_standings_scope_both_returns_player_rows_with_combined_credit(
    mock_league_repo: AsyncMock,
    mock_match_repo: AsyncMock,
) -> None:
    league = make_league()
    league.register_players_and_pair("alice", "bob")
    league.register_players_and_pair("charlie", "diana")
    pair1 = league.pairs[0]
    pair2 = league.pairs[1]
    doubles = make_match(league.league_id, pair1.pair_id, pair2.pair_id, "6", "3")
    singles = _singles_match(league, "charlie", "alice")
    singles_repo = AsyncMock()
    singles_repo.get_all_by_league.return_value = [singles]
    mock_league_repo.get_by_id.return_value = league
    mock_match_repo.get_all_by_league.return_value = [doubles]

    result = await GetStandingsUseCase(
        mock_league_repo,
        mock_match_repo,
        singles_repo,
    ).execute(GetStandingsQuery(league_id=str(league.league_id), scope="both"))

    assert {e.subject_kind for e in result.entries} == {"player"}
    alice = next(e for e in result.entries if e.nickname == "alice")
    assert alice.matches_played == 2
    assert alice.wins == 1
    assert alice.losses == 1


async def test_match_history_scope_both_merges_doubles_and_singles_newest_first(
    mock_league_repo: AsyncMock,
    mock_match_repo: AsyncMock,
) -> None:
    league = make_league()
    league.register_players_and_pair("alice", "bob")
    league.register_players_and_pair("charlie", "diana")
    pair1 = league.pairs[0]
    pair2 = league.pairs[1]
    doubles = make_match(league.league_id, pair1.pair_id, pair2.pair_id, "6", "3")
    doubles.created_at = datetime(2026, 5, 1, 12, 0)
    singles = _singles_match(league, "charlie", "alice")
    singles.created_at = datetime(2026, 5, 2, 12, 0)
    singles_repo = AsyncMock()
    singles_repo.get_all_by_league.return_value = [singles]
    mock_league_repo.get_by_id.return_value = league
    mock_match_repo.get_all_by_league.return_value = [doubles]

    records = await GetMatchHistoryUseCase(
        mock_league_repo,
        mock_match_repo,
        singles_repo,
    ).execute(GetMatchHistoryQuery(league_id=str(league.league_id), scope="both"))

    assert [r.match_format for r in records] == ["singles", "doubles"]
    assert records[0].player1_nickname == "charlie"
    assert records[0].player2_nickname == "alice"
