"""Unit tests for EditPlayerNicknameUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.edit_player_nickname_use_case import (
    EditPlayerNicknameCommand,
    EditPlayerNicknameUseCase,
)
from app.domain.exceptions import (
    LeagueNotFoundError,
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestEditPlayerNicknameUseCase:
    def _use_case(self, league_repo: AsyncMock) -> EditPlayerNicknameUseCase:
        return EditPlayerNicknameUseCase(league_repo)

    def _league_with_players(self, host_token: str = "valid-token"):
        league = make_league(host_token=host_token)
        league.register_players_and_team("alice", "bob")
        return league

    async def test_happy_path_returns_updated_player(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = self._league_with_players()
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            EditPlayerNicknameCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                player_id=str(alice.player_id),
                new_nickname="alicia",
            )
        )

        assert result.player_id == str(alice.player_id.value)
        assert result.new_nickname == "alicia"

    async def test_nickname_stored_lowercased(self, mock_league_repo: AsyncMock) -> None:
        league = self._league_with_players()
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        result = await use_case.execute(
            EditPlayerNicknameCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                player_id=str(alice.player_id),
                new_nickname="ALICIA",
            )
        )

        assert result.new_nickname == "alicia"

    async def test_league_saved_after_update(self, mock_league_repo: AsyncMock) -> None:
        league = self._league_with_players()
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        await use_case.execute(
            EditPlayerNicknameCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                player_id=str(alice.player_id),
                new_nickname="alicia",
            )
        )

        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    player_id="00000000-0000-0000-0000-000000000001",
                    new_nickname="newname",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = self._league_with_players(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    player_id="00000000-0000-0000-0000-000000000001",
                    new_nickname="newname",
                )
            )

    async def test_player_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        import uuid

        league = self._league_with_players()
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(PlayerNotFoundError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    player_id=str(uuid.uuid4()),
                    new_nickname="newname",
                )
            )

    async def test_duplicate_nickname_raises(self, mock_league_repo: AsyncMock) -> None:
        league = self._league_with_players()
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(NicknameAlreadyInUseError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    player_id=str(alice.player_id),
                    new_nickname="bob",
                )
            )

    async def test_duplicate_detected_case_insensitively(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = self._league_with_players()
        alice = next(p for p in league.players if p.nickname.value == "alice")

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(NicknameAlreadyInUseError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    player_id=str(alice.player_id),
                    new_nickname="BOB",
                )
            )

    async def test_unauthorized_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        league = self._league_with_players(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                EditPlayerNicknameCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    player_id="00000000-0000-0000-0000-000000000001",
                    new_nickname="newname",
                )
            )

        mock_league_repo.save.assert_not_awaited()
