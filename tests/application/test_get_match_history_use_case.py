"""Unit tests for GetMatchHistoryUseCase."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_match_history_use_case import (
    GetMatchHistoryQuery,
    GetMatchHistoryUseCase,
    MatchHistoryRecord,
)
from app.domain.aggregates.league.value_objects import PairId
from app.domain.exceptions import LeagueNotFoundError
from tests.application.conftest import make_league, make_match


class TestGetMatchHistoryUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetMatchHistoryUseCase:
        return GetMatchHistoryUseCase(league_repo, match_repo)

    async def test_returns_empty_list_for_league_with_no_matches(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

        assert result == []

    async def test_returns_match_history_records(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair1 = league.pairs[0]
        pair2 = league.pairs[1]
        match = make_match(league.league_id, pair1.pair_id, pair2.pair_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

        assert len(result) == 1
        assert isinstance(result[0], MatchHistoryRecord)
        assert result[0].match_id == str(match.match_id)
        assert result[0].pair1_score == "6"
        assert result[0].pair2_score == "3"

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetMatchHistoryQuery(league_id="00000000-0000-0000-0000-000000000000")
            )

    async def test_player_nicknames_resolved_correctly(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair1 = league.pairs[0]
        pair2 = league.pairs[1]
        match = make_match(league.league_id, pair1.pair_id, pair2.pair_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

        record = result[0]
        pair1_nicks = {record.pair1_player1_nickname, record.pair1_player2_nickname}
        pair2_nicks = {record.pair2_player1_nickname, record.pair2_player2_nickname}

        pair1_expected = {
            p.nickname.value
            for p in league.players
            if p.player_id in (pair1.player_id_1, pair1.player_id_2)
        }
        pair2_expected = {
            p.nickname.value
            for p in league.players
            if p.player_id in (pair2.player_id_1, pair2.player_id_2)
        }

        assert pair1_nicks == pair1_expected
        assert pair2_nicks == pair2_expected

    async def test_records_sorted_newest_first(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        pair1 = league.pairs[0]
        pair2 = league.pairs[1]

        older_match = make_match(league.league_id, pair1.pair_id, pair2.pair_id)
        older_match.created_at = datetime(2025, 1, 1)

        newer_match = make_match(league.league_id, pair2.pair_id, pair1.pair_id)
        newer_match.created_at = datetime(2025, 6, 1)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [older_match, newer_match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

        assert result[0].match_id == str(newer_match.match_id)
        assert result[1].match_id == str(older_match.match_id)

    async def test_unknown_pair_shows_unknown_nicknames(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        orphan_pair_id = PairId.generate()
        other_pair_id = PairId.generate()
        match = make_match(league.league_id, orphan_pair_id, other_pair_id)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetMatchHistoryQuery(league_id=str(league.league_id)))

        assert result[0].pair1_player1_nickname == "unknown"
        assert result[0].pair2_player1_nickname == "unknown"
