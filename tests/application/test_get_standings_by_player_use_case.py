"""Unit tests for GetStandingsByPlayerUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_standings_by_player_use_case import (
    GetStandingsByPlayerQuery,
    GetStandingsByPlayerUseCase,
)
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.domain.services.standings_calculator import StandingsEntry
from tests.application.conftest import make_league, make_match


class TestGetStandingsByPlayerUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetStandingsByPlayerUseCase:
        return GetStandingsByPlayerUseCase(league_repo, match_repo)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetStandingsByPlayerQuery(
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
                GetStandingsByPlayerQuery(
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
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="ALICE")
        )
        assert len(result) == 1
        assert isinstance(result[0], StandingsEntry)

    async def test_returns_empty_when_player_has_no_team(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )
        assert result == []

    async def test_returns_single_entry_with_league_rank(
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
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="charlie")
        )

        assert len(result) == 1
        assert result[0].team_id == str(team2.team_id.value)
        assert result[0].wins == 0
        assert result[0].losses == 1
        assert result[0].rank == 2

    async def test_match_repo_queried_with_league_id(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            GetStandingsByPlayerQuery(league_id=str(league.league_id), player_name="alice")
        )

        mock_match_repo.get_all_by_league.assert_awaited_once_with(league.league_id)
