"""Unit tests for player alias use cases."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.add_alias_to_player_use_case import (
    AddAliasToPlayerCommand,
    AddAliasToPlayerUseCase,
)
from app.application.use_cases.remove_alias_from_player_use_case import (
    RemoveAliasFromPlayerCommand,
    RemoveAliasFromPlayerUseCase,
)
from app.domain.exceptions import (
    LeagueNotFoundError,
    NicknameAlreadyInUseError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestAddAliasToPlayerUseCase:
    def _use_case(self, league_repo: AsyncMock) -> AddAliasToPlayerUseCase:
        return AddAliasToPlayerUseCase(league_repo)

    async def test_happy_path_adds_alias_and_saves(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        alice = league.add_players(["alice"])[0]
        mock_league_repo.get_by_id_with_lock.return_value = league

        result = await self._use_case(mock_league_repo).execute(
            AddAliasToPlayerCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                player_id=str(alice.player_id.value),
                alias="Ali",
            )
        )

        assert result.nickname == "alice"
        assert result.aliases == ["ali"]
        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_league_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None

        with pytest.raises(LeagueNotFoundError):
            await self._use_case(mock_league_repo).execute(
                AddAliasToPlayerCommand(
                    host_token="token",
                    league_id=str(uuid.uuid4()),
                    player_id=str(uuid.uuid4()),
                    alias="ali",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        alice = league.add_players(["alice"])[0]
        mock_league_repo.get_by_id_with_lock.return_value = league

        with pytest.raises(UnauthorizedError):
            await self._use_case(mock_league_repo).execute(
                AddAliasToPlayerCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    player_id=str(alice.player_id.value),
                    alias="ali",
                )
            )
        mock_league_repo.save.assert_not_awaited()

    async def test_collision_does_not_save(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="valid-token")
        alice, _ = league.add_players(["alice", "bob"])
        mock_league_repo.get_by_id_with_lock.return_value = league

        with pytest.raises(NicknameAlreadyInUseError):
            await self._use_case(mock_league_repo).execute(
                AddAliasToPlayerCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    player_id=str(alice.player_id.value),
                    alias="bob",
                )
            )
        mock_league_repo.save.assert_not_awaited()


class TestRemoveAliasFromPlayerUseCase:
    def _use_case(self, league_repo: AsyncMock) -> RemoveAliasFromPlayerUseCase:
        return RemoveAliasFromPlayerUseCase(league_repo)

    async def test_happy_path_removes_alias_and_saves(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        alice = league.add_players(["alice"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        mock_league_repo.get_by_id_with_lock.return_value = league

        result = await self._use_case(mock_league_repo).execute(
            RemoveAliasFromPlayerCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                player_id=str(alice.player_id.value),
                alias="ali",
            )
        )

        assert result.nickname == "alice"
        assert result.aliases == []
        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_wrong_host_token_does_not_save(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        alice = league.add_players(["alice"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        mock_league_repo.get_by_id_with_lock.return_value = league

        with pytest.raises(UnauthorizedError):
            await self._use_case(mock_league_repo).execute(
                RemoveAliasFromPlayerCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    player_id=str(alice.player_id.value),
                    alias="ali",
                )
            )
        mock_league_repo.save.assert_not_awaited()
