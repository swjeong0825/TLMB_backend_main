"""Unit tests for EditMatchScoreUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.domain.aggregates.league.value_objects import TeamId
from app.domain.exceptions import (
    InvalidSetScoreError,
    LeagueNotFoundError,
    MatchNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league, make_match


class TestEditMatchScoreUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> EditMatchScoreUseCase:
        return EditMatchScoreUseCase(league_repo, match_repo)

    async def test_happy_path_returns_updated_score(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, TeamId.generate(), TeamId.generate(), "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            EditMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                team1_score="4",
                team2_score="6",
            )
        )

        assert result.match_id == str(match.match_id)
        assert result.team1_score == "4"
        assert result.team2_score == "6"

    async def test_match_score_is_persisted(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, TeamId.generate(), TeamId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            EditMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                team1_score="7",
                team2_score="5",
            )
        )

        mock_match_repo.save.assert_awaited_once_with(match)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
                    team1_score="6",
                    team2_score="3",
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
                EditMatchScoreCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    team1_score="6",
                    team2_score="3",
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
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_invalid_score_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, TeamId.generate(), TeamId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(InvalidSetScoreError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    team1_score="-1",
                    team2_score="6",
                )
            )

    async def test_negative_score_does_not_save(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, TeamId.generate(), TeamId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(InvalidSetScoreError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    team1_score="abc",
                    team2_score="6",
                )
            )

        mock_match_repo.save.assert_not_awaited()
