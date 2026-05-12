"""Unit tests for GetEligiblePlayersUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_eligible_players_use_case import (
    EligiblePlayersView,
    GetEligiblePlayersQuery,
    GetEligiblePlayersUseCase,
)
from app.domain.exceptions import LeagueNotFoundError
from tests.application.conftest import make_league


class TestGetEligiblePlayersUseCase:
    def _use_case(self, league_repo: AsyncMock) -> GetEligiblePlayersUseCase:
        return GetEligiblePlayersUseCase(league_repo)

    async def test_empty_list_for_new_league(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetEligiblePlayersQuery(league_id=str(league.league_id))
        )
        assert isinstance(result, EligiblePlayersView)
        assert result.eligible_players == []

    async def test_returns_all_eligible_entries(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.add_eligible_players(["alex", "daniel", "jason"])
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetEligiblePlayersQuery(league_id=str(league.league_id))
        )
        nicks = [e.nickname for e in result.eligible_players]
        # Sorted alphabetically for stable display ordering.
        assert nicks == sorted(nicks)
        assert set(nicks) == {"alex", "daniel", "jason"}

    async def test_each_entry_has_id_and_nickname(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        added = league.add_eligible_players(["alex"])
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetEligiblePlayersQuery(league_id=str(league.league_id))
        )
        assert len(result.eligible_players) == 1
        entry = result.eligible_players[0]
        assert entry.eligible_player_id == str(added[0].eligible_player_id.value)
        assert entry.nickname == "alex"

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetEligiblePlayersQuery(
                    league_id="00000000-0000-0000-0000-000000000000"
                )
            )
