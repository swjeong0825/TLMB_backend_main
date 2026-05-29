"""Unit tests for DeleteMatchUseCase."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.delete_match_use_case import DeleteMatchCommand, DeleteMatchUseCase
from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchDeleteWindowExpiredError,
    MatchNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league, make_match


class TestDeleteMatchUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> DeleteMatchUseCase:
        return DeleteMatchUseCase(league_repo, match_repo)

    async def test_happy_path_deletes_match(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        pair1_id = PairId.generate()
        pair2_id = PairId.generate()
        match = make_match(league.league_id, pair1_id, pair2_id)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match

        use_case = self._use_case(mock_league_repo, mock_match_repo)
        await use_case.execute(
            DeleteMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
            )
        )

        mock_match_repo.delete.assert_awaited_once_with(match.match_id, league.league_id)
        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_recomputes_latest_match_date_after_delete(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        pair1_id = PairId.generate()
        pair2_id = PairId.generate()
        deleted_match = make_match(league.league_id, pair1_id, pair2_id)
        remaining_match = make_match(league.league_id, pair1_id, pair2_id)
        remaining_match.created_at = datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = deleted_match
        mock_match_repo.get_latest_by_league.return_value = remaining_match

        use_case = self._use_case(mock_league_repo, mock_match_repo)
        await use_case.execute(
            DeleteMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(deleted_match.match_id),
            )
        )

        assert league.latest_match_date == date(2026, 5, 24)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
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
                DeleteMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_match_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_unauthorized_does_not_call_delete(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

        mock_match_repo.delete.assert_not_awaited()

    async def test_league_repo_queried_with_correct_league_id(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token="token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

        mock_league_repo.get_by_id_with_lock.assert_awaited_once_with(league.league_id)


class TestDeleteMatchUseCasePlayerWindow:
    """Player-delete window (no `X-Host-Token`) behavior.

    Mirrors `TestEditMatchScoreUseCasePlayerWindow`. The use case treats
    `host_token=None` as a player call: skip auth, enforce
    `now - match.created_at <= window_seconds`. Admin path
    (`host_token` set) keeps working regardless of `created_at`.
    """

    def _use_case(
        self,
        league_repo: AsyncMock,
        match_repo: AsyncMock,
        window_seconds: int = 600,
    ) -> DeleteMatchUseCase:
        return DeleteMatchUseCase(
            league_repo, match_repo, window_seconds=window_seconds
        )

    async def test_player_inside_window_deletes(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        pair1_id = PairId.generate()
        pair2_id = PairId.generate()
        match = make_match(league.league_id, pair1_id, pair2_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=30)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=600)

        await use_case.execute(
            DeleteMatchCommand(
                host_token=None,
                league_id=str(league.league_id),
                match_id=str(match.match_id),
            )
        )

        mock_match_repo.delete.assert_awaited_once_with(match.match_id, league.league_id)

    async def test_player_outside_window_raises_expired(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=1200)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=600)

        with pytest.raises(MatchDeleteWindowExpiredError) as exc_info:
            await use_case.execute(
                DeleteMatchCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                )
            )

        assert exc_info.value.match_id == str(match.match_id)
        assert exc_info.value.window_seconds == 600
        assert exc_info.value.age_seconds >= 1200
        mock_match_repo.delete.assert_not_awaited()

    async def test_admin_bypasses_window_even_when_match_is_old(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(days=30)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=60)

        await use_case.execute(
            DeleteMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
            )
        )

        mock_match_repo.delete.assert_awaited_once_with(match.match_id, league.league_id)

    async def test_player_no_created_at_is_rejected(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        # `Match.create` leaves `created_at` as None for non-persisted
        # aggregates. A player request hitting such a match is rejected
        # rather than allowed (fail-closed: defense against unexpected
        # state).
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = None

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchDeleteWindowExpiredError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                )
            )

        mock_match_repo.delete.assert_not_awaited()

    async def test_player_league_not_found_raises_league_not_found(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id_with_lock.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token=None,
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_player_match_not_found_raises_match_not_found(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                DeleteMatchCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

    async def test_default_window_seconds_is_600(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        # Constructed without an explicit window_seconds, the default
        # is 10 minutes. A match older than that fails for a player.
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=700)

        mock_league_repo.get_by_id_with_lock.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = DeleteMatchUseCase(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchDeleteWindowExpiredError) as exc:
            await use_case.execute(
                DeleteMatchCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                )
            )
        assert exc.value.window_seconds == 600
