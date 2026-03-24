"""Unit tests for GetLeagueRosterUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_league_roster_use_case import (
    GetLeagueRosterQuery,
    GetLeagueRosterUseCase,
    RosterView,
)
from app.domain.exceptions import LeagueNotFoundError
from tests.application.conftest import make_league


class TestGetLeagueRosterUseCase:
    def _use_case(self, league_repo: AsyncMock) -> GetLeagueRosterUseCase:
        return GetLeagueRosterUseCase(league_repo)

    async def test_returns_empty_roster_for_new_league(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        assert isinstance(result, RosterView)
        assert result.players == []
        assert result.teams == []

    async def test_players_sorted_alphabetically(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("charlie", "alice")
        league.register_players_and_team("diana", "bob")

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        nicknames = [p.nickname for p in result.players]
        assert nicknames == sorted(nicknames)

    async def test_teams_sorted_by_player1_nickname(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("charlie", "diana")
        league.register_players_and_team("alice", "bob")

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        player1_nicks = [t.player1_nickname for t in result.teams]
        assert player1_nicks == sorted(player1_nicks)

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetLeagueRosterQuery(league_id="00000000-0000-0000-0000-000000000000")
            )

    async def test_player_entry_contains_correct_fields(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        entry = next(p for p in result.players if p.nickname == "alice")
        assert entry.player_id == str(alice.player_id.value)
        assert entry.nickname == "alice"

    async def test_team_entry_contains_player_nicknames(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        team = league.teams[0]

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        assert len(result.teams) == 1
        team_entry = result.teams[0]
        assert team_entry.team_id == str(team.team_id.value)
        nicks = {team_entry.player1_nickname, team_entry.player2_nickname}
        assert nicks == {"alice", "bob"}

    async def test_roster_reflects_all_registered_players(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(GetLeagueRosterQuery(league_id=str(league.league_id)))

        assert len(result.players) == 4
        assert len(result.teams) == 2
