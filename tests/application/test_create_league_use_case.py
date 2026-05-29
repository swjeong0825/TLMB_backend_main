"""Unit tests for CreateLeagueUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.domain.exceptions import InvalidLeagueRulesError, LeagueTitleAlreadyExistsError
from tests.application.conftest import make_league


_HOST_EMAIL = "host@example.com"


class TestCreateLeagueUseCase:
    def _use_case(self, league_repo: AsyncMock) -> CreateLeagueUseCase:
        return CreateLeagueUseCase(league_repo)

    async def test_creates_league_and_returns_ids(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            CreateLeagueCommand(title="Summer League", host_email=_HOST_EMAIL, description=None)
        )

        assert result.league_id is not None
        assert result.host_token is not None

    async def test_league_id_is_non_empty_string(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            CreateLeagueCommand(title="My League", host_email=_HOST_EMAIL, description=None)
        )

        assert len(result.league_id) > 0
        assert len(result.host_token) > 0

    async def test_saves_league_to_repository(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(title="My League", host_email=_HOST_EMAIL, description="desc")
        )

        mock_league_repo.save.assert_awaited_once()

    async def test_forwards_host_email_to_aggregate(self, mock_league_repo: AsyncMock) -> None:
        """host_email is set on the aggregate at create time and reaches the
        repo via the saved League instance."""
        mock_league_repo.get_by_normalized_title.return_value = None
        saved_leagues: list = []
        mock_league_repo.save.side_effect = (
            lambda league: saved_leagues.append(league) or None
        )
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(
                title="Email League",
                host_email="Host@Example.COM",
                description=None,
            )
        )

        assert saved_leagues[0].host_email.value == "host@example.com"

    async def test_forwards_league_timezone_to_aggregate(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        saved_leagues: list = []
        mock_league_repo.save.side_effect = (
            lambda league: saved_leagues.append(league) or None
        )
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(
                title="Timezone League",
                host_email=_HOST_EMAIL,
                description=None,
                league_timezone="Asia/Seoul",
            )
        )

        assert saved_leagues[0].league_timezone.value == "Asia/Seoul"

    async def test_invalid_league_timezone_raises(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(InvalidLeagueRulesError):
            await use_case.execute(
                CreateLeagueCommand(
                    title="Bad Timezone League",
                    host_email=_HOST_EMAIL,
                    description=None,
                    league_timezone="not/a-zone",
                )
            )

    async def test_checks_title_uniqueness_with_normalized_title(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(title="  My League  ", host_email=_HOST_EMAIL, description=None)
        )

        mock_league_repo.get_by_normalized_title.assert_awaited_once_with("my league")

    async def test_duplicate_title_raises_error(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("Summer League")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(
                CreateLeagueCommand(title="Summer League", host_email=_HOST_EMAIL, description=None)
            )

    async def test_duplicate_title_case_insensitive(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("summer league")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(
                CreateLeagueCommand(title="SUMMER LEAGUE", host_email=_HOST_EMAIL, description=None)
            )

    async def test_duplicate_title_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        existing_league = make_league("Summer League")
        mock_league_repo.get_by_normalized_title.return_value = existing_league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueTitleAlreadyExistsError):
            await use_case.execute(
                CreateLeagueCommand(title="Summer League", host_email=_HOST_EMAIL, description=None)
            )

        mock_league_repo.save.assert_not_awaited()

    async def test_two_calls_produce_distinct_league_ids(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        use_case = self._use_case(mock_league_repo)

        r1 = await use_case.execute(
            CreateLeagueCommand(title="League A", host_email=_HOST_EMAIL, description=None)
        )
        r2 = await use_case.execute(
            CreateLeagueCommand(title="League B", host_email=_HOST_EMAIL, description=None)
        )

        assert r1.league_id != r2.league_id
        assert r1.host_token != r2.host_token

    async def test_seeds_initial_players_in_same_save_call(
        self, mock_league_repo: AsyncMock
    ) -> None:
        """When `initial_players` is non-empty, the use case populates the
        aggregate's roster before `save`, so both rows reach the DB in
        the same UoW transaction (no second commit)."""
        mock_league_repo.get_by_normalized_title.return_value = None
        saved_leagues: list = []
        mock_league_repo.save.side_effect = (
            lambda league: saved_leagues.append(league) or None
        )
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(
                title="Pre-registered League",
                host_email=_HOST_EMAIL,
                description=None,
                initial_players=["Alex", "Daniel", "Jason"],
            )
        )

        mock_league_repo.save.assert_awaited_once()
        assert len(saved_leagues) == 1
        league = saved_leagues[0]
        assert {p.nickname.value for p in league.players} == {
            "alex",
            "daniel",
            "jason",
        }
        assert league.pairs == []

    async def test_empty_initial_players_is_a_noop(
        self, mock_league_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_normalized_title.return_value = None
        saved_leagues: list = []
        mock_league_repo.save.side_effect = (
            lambda league: saved_leagues.append(league) or None
        )
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            CreateLeagueCommand(
                title="Empty Seed League",
                host_email=_HOST_EMAIL,
                description=None,
                initial_players=[],
            )
        )

        mock_league_repo.save.assert_awaited_once()
        assert saved_leagues[0].players == []
