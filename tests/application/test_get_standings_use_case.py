"""Unit tests for GetStandingsUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_standings_use_case import GetStandingsQuery, GetStandingsUseCase
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError
from app.domain.services.standings_calculator import StandingsEntry
from tests.application.conftest import make_league, make_match, make_player, make_team


class TestGetStandingsUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> GetStandingsUseCase:
        return GetStandingsUseCase(league_repo, match_repo)

    async def test_returns_empty_standings_for_league_with_no_matches(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

        assert result == []

    async def test_standings_computed_from_match_records(
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

        result = await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

        assert len(result) == 2
        winner = next(e for e in result if e.team_id == str(team1.team_id.value))
        assert winner.wins == 1
        assert winner.losses == 0
        assert winner.rank == 1

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetStandingsQuery(league_id="00000000-0000-0000-0000-000000000000")
            )

    async def test_match_repo_queried_with_correct_league_id(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

        mock_match_repo.get_all_by_league.assert_awaited_once_with(league.league_id)

    async def test_returns_standings_entry_objects(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        team = league.teams[0]
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = []
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

        assert len(result) == 1
        assert isinstance(result[0], StandingsEntry)

    async def test_tied_teams_both_ranked_first(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        team1 = league.teams[0]
        team2 = league.teams[1]
        m1 = make_match(league.league_id, team1.team_id, team2.team_id, "6", "3")
        m2 = make_match(league.league_id, team2.team_id, team1.team_id, "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_all_by_league.return_value = [m1, m2]
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

        assert all(e.rank == 1 for e in result)
