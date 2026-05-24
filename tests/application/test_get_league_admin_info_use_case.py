"""Unit tests for GetLeagueAdminInfoUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.get_league_admin_info_use_case import (
    GetLeagueAdminInfoQuery,
    GetLeagueAdminInfoUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@pytest.fixture
def league_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def use_case(league_repo: AsyncMock) -> GetLeagueAdminInfoUseCase:
    return GetLeagueAdminInfoUseCase(league_repo)


class TestGetLeagueAdminInfoUseCase:
    async def test_returns_host_email_for_valid_token(
        self, use_case: GetLeagueAdminInfoUseCase, league_repo: AsyncMock
    ) -> None:
        league = League.create(
            "Test League",
            None,
            "valid-token",
            host_email="  Host@Example.com ",
        )
        league_repo.get_by_id.return_value = league

        result = await use_case.execute(
            GetLeagueAdminInfoQuery(
                host_token="valid-token",
                league_id=str(league.league_id),
            )
        )

        assert result.host_email == "host@example.com"

    async def test_league_not_found_raises(
        self, use_case: GetLeagueAdminInfoUseCase, league_repo: AsyncMock
    ) -> None:
        league_repo.get_by_id.return_value = None

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                GetLeagueAdminInfoQuery(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_invalid_host_token_raises(
        self, use_case: GetLeagueAdminInfoUseCase, league_repo: AsyncMock
    ) -> None:
        league = League.create(
            "Test League",
            None,
            "valid-token",
            host_email="host@example.com",
        )
        league_repo.get_by_id.return_value = league

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                GetLeagueAdminInfoQuery(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                )
            )
