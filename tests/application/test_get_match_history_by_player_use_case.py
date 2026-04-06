"""Unit tests for GetMatchHistoryByPlayerUseCase."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.application.use_cases.get_match_history_by_player_use_case import (
    GetMatchHistoryByPlayerQuery,
    GetMatchHistoryByPlayerUseCase,
)
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from tests.application.conftest import make_league, make_match


class TestGetMatchHistoryByPlayerUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetMatchHistoryByPlayerUseCase:
        return GetMatchHistoryByPlayerUseCase(league_repo, match_repo)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetMatchHistoryByPlayerQuery(
                    league_id="00000000-0000-0000-0000-000000000000",
                    player_name="alice",
                )
            )

    async def test_player_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                GetMatchHistoryByPlayerQuery(
                    league_id=str(league.league_id),
                    player_name="unknown_player",
                )
            )

    async def test_player_name_lookup_is_case_insensitive(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="ALICE")
        )
        assert result == []

    async def test_returns_empty_list_when_player_has_no_team(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result == []
        mock_match_repo.get_all_by_league.assert_not_called()

    async def test_returns_empty_list_when_player_has_no_matches(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result == []

    async def test_returns_only_matches_involving_players_team(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        league.register_players_and_team("edgar", "frank")
        team_alice = league.teams[0]
        team_charlie = league.teams[1]
        team_edgar = league.teams[2]

        match_with_alice = make_match(league.league_id, team_alice.team_id, team_charlie.team_id, "6", "3")
        match_without_alice = make_match(league.league_id, team_charlie.team_id, team_edgar.team_id, "4", "6")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match_with_alice, match_without_alice]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        assert result[0].match_id == str(match_with_alice.match_id)

    async def test_returned_records_contain_correct_nicknames(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team1 = league.teams[0]
        team2 = league.teams[1]
        match = make_match(league.league_id, team1.team_id, team2.team_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        record = result[0]
        assert isinstance(record, MatchHistoryRecord)
        team1_nicks = {record.team1_player1_nickname, record.team1_player2_nickname}
        team2_nicks = {record.team2_player1_nickname, record.team2_player2_nickname}
        assert team1_nicks == {
            p.nickname.value
            for p in league.players
            if p.player_id in (team1.player_id_1, team1.player_id_2)
        }
        assert team2_nicks == {
            p.nickname.value
            for p in league.players
            if p.player_id in (team2.player_id_1, team2.player_id_2)
        }

    async def test_results_sorted_newest_first(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team1 = league.teams[0]
        team2 = league.teams[1]

        older_match = make_match(league.league_id, team1.team_id, team2.team_id)
        older_match.created_at = datetime(2025, 1, 1)

        newer_match = make_match(league.league_id, team2.team_id, team1.team_id)
        newer_match.created_at = datetime(2025, 6, 1)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [older_match, newer_match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert result[0].match_id == str(newer_match.match_id)
        assert result[1].match_id == str(older_match.match_id)

    async def test_also_returns_matches_where_player_team_is_team2(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team_alice = league.teams[0]
        team_charlie = league.teams[1]

        match = make_match(league.league_id, team_charlie.team_id, team_alice.team_id, "3", "6")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [match]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetMatchHistoryByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        assert len(result) == 1
        assert result[0].match_id == str(match.match_id)
