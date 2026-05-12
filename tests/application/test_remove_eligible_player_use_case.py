"""Unit tests for RemoveEligiblePlayerUseCase."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.remove_eligible_player_use_case import (
    RemoveEligiblePlayerCommand,
    RemoveEligiblePlayerUseCase,
)
from app.domain.exceptions import (
    EligiblePlayerNotFoundError,
    LeagueNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestRemoveEligiblePlayerUseCase:
    def _use_case(self, league_repo: AsyncMock) -> RemoveEligiblePlayerUseCase:
        return RemoveEligiblePlayerUseCase(league_repo)

    async def test_happy_path_removes_and_saves(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        added = league.add_eligible_players(["alex", "daniel"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            RemoveEligiblePlayerCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                eligible_player_id=str(added[0].eligible_player_id.value),
            )
        )

        nicks = {e.nickname.value for e in league.eligible_players}
        assert nicks == {"daniel"}
        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                RemoveEligiblePlayerCommand(
                    host_token="any",
                    league_id="00000000-0000-0000-0000-000000000000",
                    eligible_player_id=str(uuid.uuid4()),
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        added = league.add_eligible_players(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                RemoveEligiblePlayerCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    eligible_player_id=str(added[0].eligible_player_id.value),
                )
            )

    async def test_unauthorized_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="correct-token")
        added = league.add_eligible_players(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                RemoveEligiblePlayerCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    eligible_player_id=str(added[0].eligible_player_id.value),
                )
            )

        mock_league_repo.save.assert_not_awaited()

    async def test_unknown_eligible_player_id_raises_404_class(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        league.add_eligible_players(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(EligiblePlayerNotFoundError):
            await use_case.execute(
                RemoveEligiblePlayerCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    eligible_player_id=str(uuid.uuid4()),
                )
            )
