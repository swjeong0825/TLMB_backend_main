"""Unit tests for AddPlayersUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.add_players_use_case import (
    AddPlayersCommand,
    AddPlayersUseCase,
)
from app.domain.exceptions import (
    LeagueNotFoundError,
    NicknameAlreadyInUseError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestAddPlayersUseCase:
    def _use_case(self, league_repo: AsyncMock) -> AddPlayersUseCase:
        return AddPlayersUseCase(league_repo)

    async def test_happy_path_returns_new_players(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            AddPlayersCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["Alex", "Daniel"],
            )
        )

        assert [p.nickname for p in result.players] == ["alex", "daniel"]
        assert [p.rating for p in result.players] == [None, None]
        assert all(p.player_id for p in result.players)

    async def test_happy_path_can_include_ratings(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            AddPlayersCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["Alex", "Daniel"],
                ratings=[3.5, None],
            )
        )

        assert [(p.nickname, p.rating) for p in result.players] == [
            ("alex", 3.5),
            ("daniel", None),
        ]

    async def test_persists_via_save(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            AddPlayersCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["alex"],
            )
        )

        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_creates_player_rows_on_saved_aggregate(
        self, mock_league_repo: AsyncMock
    ) -> None:
        """Players are added directly to the saved aggregate's roster so a
        single repo.save persists everything in one transaction."""
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        saved: list = []
        mock_league_repo.save.side_effect = (
            lambda lg: saved.append(lg) or None
        )
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            AddPlayersCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                nicknames=["Alex", "Daniel"],
            )
        )

        assert len(saved) == 1
        assert {p.nickname.value for p in saved[0].players} == {"alex", "daniel"}

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                AddPlayersCommand(
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
                AddPlayersCommand(
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
                AddPlayersCommand(
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
        league.add_players(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_league_repo.save.reset_mock()
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(NicknameAlreadyInUseError):
            await use_case.execute(
                AddPlayersCommand(
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

        with pytest.raises(NicknameAlreadyInUseError):
            await use_case.execute(
                AddPlayersCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    nicknames=["Alex", "ALEX"],
                )
            )

    async def test_failed_batch_does_not_save(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        league.add_players(["alex"])
        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_league_repo.save.reset_mock()
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(NicknameAlreadyInUseError):
            await use_case.execute(
                AddPlayersCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    nicknames=["daniel", "alex"],
                )
            )

        mock_league_repo.save.assert_not_awaited()
