"""Unit tests for DeletePairUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.delete_pair_use_case import DeletePairCommand, DeletePairUseCase
from app.domain.exceptions import (
    LeagueNotFoundError,
    PairHasMatchesError,
    PairNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


class TestDeletePairUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> DeletePairUseCase:
        return DeletePairUseCase(league_repo, match_repo)

    async def test_happy_path_deletes_pair(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, pair = league.register_players_and_pair("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_pair.return_value = False
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            DeletePairCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                pair_id=str(pair.pair_id),
            )
        )

        mock_league_repo.save.assert_awaited_once()
        assert len(league.pairs) == 0

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                DeletePairCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    pair_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeletePairCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    pair_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_pair_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PairNotFoundError):
            await use_case.execute(
                DeletePairCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    pair_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_pair_with_matches_raises_pair_has_matches_error(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, pair = league.register_players_and_pair("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_pair.return_value = True
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PairHasMatchesError):
            await use_case.execute(
                DeletePairCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    pair_id=str(pair.pair_id),
                )
            )

    async def test_pair_has_matches_does_not_save(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, pair = league.register_players_and_pair("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_pair.return_value = True
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(PairHasMatchesError):
            await use_case.execute(
                DeletePairCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    pair_id=str(pair.pair_id),
                )
            )

        mock_league_repo.save.assert_not_awaited()

    async def test_has_matches_checked_with_correct_pair_and_league(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        _, pair = league.register_players_and_pair("alice", "bob")

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.has_matches_for_pair.return_value = False
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            DeletePairCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                pair_id=str(pair.pair_id),
            )
        )

        mock_match_repo.has_matches_for_pair.assert_awaited_once_with(
            pair.pair_id, league.league_id
        )
