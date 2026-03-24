"""Unit tests for DeleteMatchUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.delete_match_use_case import DeleteMatchCommand, DeleteMatchUseCase
from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import LeagueNotFoundError, MatchNotFoundError, UnauthorizedError
from tests.application.conftest import make_league, make_match


class TestDeleteMatchUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> DeleteMatchUseCase:
        return DeleteMatchUseCase(league_repo, match_repo)

    async def test_happy_path_deletes_match(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        team1_id = TeamId.generate()
        team2_id = TeamId.generate()
        match = make_match(league.league_id, team1_id, team2_id)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match

        use_case = self._use_case(mock_league_repo, mock_match_repo)
        await use_case.execute(
            DeleteMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
            )
        )

        mock_match_repo.delete.assert_awaited_once_with(match.match_id, league.league_id)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_match_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_unauthorized_does_not_call_delete(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

        mock_match_repo.delete.assert_not_awaited()

    async def test_league_repo_queried_with_correct_league_id(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="token")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

        mock_league_repo.get_by_id.assert_awaited_once_with(league.league_id)
