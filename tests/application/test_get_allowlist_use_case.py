"""Unit tests for GetAllowlistUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_allowlist_use_case import (
    AllowlistView,
    GetAllowlistQuery,
    GetAllowlistUseCase,
)
from app.domain.exceptions import LeagueNotFoundError
from tests.application.conftest import make_league


class TestGetAllowlistUseCase:
    def _use_case(self, league_repo: AsyncMock) -> GetAllowlistUseCase:
        return GetAllowlistUseCase(league_repo)

    async def test_empty_list_for_new_league(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetAllowlistQuery(league_id=str(league.league_id))
        )
        assert isinstance(result, AllowlistView)
        assert result.allowlist == []

    async def test_returns_all_allowlist_entries(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        league.add_allowlist_entries(["alex", "daniel", "jason"])
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetAllowlistQuery(league_id=str(league.league_id))
        )
        nicks = [e.nickname for e in result.allowlist]
        # Sorted alphabetically for stable display ordering.
        assert nicks == sorted(nicks)
        assert set(nicks) == {"alex", "daniel", "jason"}

    async def test_each_entry_has_id_and_nickname(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        added = league.add_allowlist_entries(["alex"])
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            GetAllowlistQuery(league_id=str(league.league_id))
        )
        assert len(result.allowlist) == 1
        entry = result.allowlist[0]
        assert entry.allowlist_entry_id == str(added[0].allowlist_entry_id.value)
        assert entry.nickname == "alex"

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetAllowlistQuery(
                    league_id="00000000-0000-0000-0000-000000000000"
                )
            )
