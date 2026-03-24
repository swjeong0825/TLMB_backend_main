"""Unit tests for CreateLeagueUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.domain.exceptions import LeagueTitleAlreadyExistsError
from tests.application.conftest import make_league


class TestCreateLeagueUseCase:
    def _use_case(self, league_repo: AsyncMock) -> CreateLeagueUseCase:
        return CreateLeagueUseCase(league_repo)

    async def test_creates_league_and_returns_ids(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(CreateLeagueCommand(title="Summer League", description=None))

        assert result.league_id is not None
        assert result.host_token is not None

    async def test_league_id_is_non_empty_string(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(CreateLeagueCommand(title="My League", description=None))

        assert len(result.league_id) > 0
        assert len(result.host_token) > 0

    async def test_saves_league_to_repository(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(CreateLeagueCommand(title="My League", description="desc"))

        mock_league_repo.save.assert_awaited_once()

    async def test_checks_title_uniqueness_with_normalized_title(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(CreateLeagueCommand(title="  My League  ", description=None))

        mock_league_repo.get_by_normalized_title.assert_awaited_once_with("my league")

    async def test_duplicate_title_raises_error(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("Summer League")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(CreateLeagueCommand(title="Summer League", description=None))

    async def test_duplicate_title_case_insensitive(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("summer league")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(CreateLeagueCommand(title="SUMMER LEAGUE", description=None))

    async def test_duplicate_title_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("Summer League")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(CreateLeagueCommand(title="Summer League", description=None))

        mock_league_repo.save.assert_not_awaited()

    async def test_two_calls_produce_distinct_league_ids(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        r1 = await use_case.execute(CreateLeagueCommand(title="League A", description=None))
        r2 = await use_case.execute(CreateLeagueCommand(title="League B", description=None))

        assert r1.league_id != r2.league_id
        assert r1.host_token != r2.host_token
