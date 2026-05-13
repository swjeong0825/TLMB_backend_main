"""Unit tests for AddAllowlistEntriesUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.add_allowlist_entries_use_case import (
    AddAllowlistEntriesCommand,
    AddAllowlistEntriesUseCase,
)
from app.domain.exceptions import (
    AllowlistNicknameAlreadyExistsError,
    LeagueNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestAddAllowlistEntriesUseCase:
    def _use_case(self, league_repo: AsyncMock) -> AddAllowlistEntriesUseCase:
        return AddAllowlistEntriesUseCase(league_repo)

    async def test_happy_path_returns_new_entries(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            AddAllowlistEntriesCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["Alex", "Daniel"],
            )
        )

        assert [e.nickname for e in result.allowlist] == ["alex", "daniel"]
        assert all(e.allowlist_entry_id for e in result.allowlist)

    async def test_persists_via_save(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            AddAllowlistEntriesCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["alex"],
            )
        )

        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="any",
                    league_id="00000000-0000-0000-0000-000000000000",
                    nicknames=["alex"],
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    nicknames=["alex"],
                )
            )

    async def test_unauthorized_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    nicknames=["alex"],
                )
            )

        mock_league_repo.save.assert_not_awaited()

    async def test_duplicate_against_existing_raises(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        league.add_allowlist_entries(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    nicknames=["alex"],
                )
            )

    async def test_duplicate_inside_batch_raises(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    nicknames=["Alex", "ALEX"],
                )
            )

    async def test_failed_batch_does_not_save(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        league.add_allowlist_entries(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        # Reset the call count to ignore the in-test setup save above (it
        # didn't happen here — make_league + add_allowlist_entries is in-memory).
        mock_league_repo.save.reset_mock()
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            await use_case.execute(
                AddAllowlistEntriesCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    nicknames=["daniel", "alex"],
                )
            )

        mock_league_repo.save.assert_not_awaited()
