"""Unit tests for DeleteTeamUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.delete_team_use_case import DeleteTeamCommand, DeleteTeamUseCase
from app.domain.exceptions import (
    LeagueNotFoundError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestDeleteTeamUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> DeleteTeamUseCase:
        return DeleteTeamUseCase(league_repo, match_repo)

    async def test_happy_path_deletes_team(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, team = league.register_players_and_team("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_team.return_value = False
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            DeleteTeamCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                team_id=str(team.team_id),
            )
        )

        mock_league_repo.save.assert_awaited_once()
        assert len(league.teams) == 0

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                DeleteTeamCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    team_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeleteTeamCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    team_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_team_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(TeamNotFoundError):
            await use_case.execute(
                DeleteTeamCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    team_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_team_with_matches_raises_team_has_matches_error(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, team = league.register_players_and_team("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_team.return_value = True
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(TeamHasMatchesError):
            await use_case.execute(
                DeleteTeamCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    team_id=str(team.team_id),
                )
            )

    async def test_team_has_matches_does_not_save(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, team = league.register_players_and_team("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_team.return_value = True
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(TeamHasMatchesError):
            await use_case.execute(
                DeleteTeamCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    team_id=str(team.team_id),
                )
            )

        mock_league_repo.save.assert_not_awaited()

    async def test_has_matches_checked_with_correct_team_and_league(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, team = league.register_players_and_team("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_team.return_value = False
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            DeleteTeamCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                team_id=str(team.team_id),
            )
        )

        mock_match_repo.has_matches_for_team.assert_awaited_once_with(
            team.team_id, league.league_id
        )
