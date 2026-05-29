"""Unit tests for EditMatchScoreUseCase."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.domain.aggregates.league.value_objects import PairId
from app.domain.exceptions import (
    InvalidSetScoreError,
    LeagueNotFoundError,
    MatchEditWindowExpiredError,
    MatchNotFoundError,
    UnauthorizedError,
)
from tests.application.conftest import make_league, make_match


class TestEditMatchScoreUseCase:
    def _use_case(
        self, league_repo: AsyncMock, match_repo: AsyncMock
    ) -> EditMatchScoreUseCase:
        return EditMatchScoreUseCase(league_repo, match_repo)

    async def test_happy_path_returns_updated_score(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate(), "6", "3")

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        result = await use_case.execute(
            EditMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                pair1_score="4",
                pair2_score="6",
            )
        )

        assert result.match_id == str(match.match_id)
        assert result.pair1_score == "4"
        assert result.pair2_score == "6"

    async def test_match_score_is_persisted(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        await use_case.execute(
            EditMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                pair1_score="7",
                pair2_score="5",
            )
        )

        mock_match_repo.save.assert_awaited_once_with(match)

    async def test_league_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="token",
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_wrong_host_token_raises_unauthorized(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_match_not_found_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_invalid_score_raises(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(InvalidSetScoreError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    pair1_score="-1",
                    pair2_score="6",
                )
            )

    async def test_negative_score_does_not_save(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(InvalidSetScoreError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    pair1_score="abc",
                    pair2_score="6",
                )
            )

        mock_match_repo.save.assert_not_awaited()


class TestEditMatchScoreUseCasePlayerWindow:
    """Player-edit window (no `X-Host-Token`) behavior.

    The use case treats `host_token=None` as a player call: skip auth,
    enforce the `now - match.created_at <= window_seconds` check. When
    `host_token` is provided, the admin path keeps working regardless
    of `created_at`.
    """

    def _use_case(
        self,
        league_repo: AsyncMock,
        match_repo: AsyncMock,
        window_seconds: int = 3600,
    ) -> EditMatchScoreUseCase:
        return EditMatchScoreUseCase(
            league_repo, match_repo, window_seconds=window_seconds
        )

    async def test_player_inside_window_succeeds(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=3600)

        result = await use_case.execute(
            EditMatchScoreCommand(
                host_token=None,
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                pair1_score="7",
                pair2_score="5",
            )
        )

        assert result.pair1_score == "7"
        assert result.pair2_score == "5"
        mock_match_repo.save.assert_awaited_once_with(match)

    async def test_player_outside_window_raises_expired(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=3600)

        with pytest.raises(MatchEditWindowExpiredError) as exc_info:
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    pair1_score="7",
                    pair2_score="5",
                )
            )

        assert exc_info.value.match_id == str(match.match_id)
        assert exc_info.value.window_seconds == 3600
        assert exc_info.value.age_seconds >= 7200
        mock_match_repo.save.assert_not_awaited()

    async def test_admin_bypasses_window_even_when_match_is_old(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(days=30)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo, window_seconds=60)

        result = await use_case.execute(
            EditMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                pair1_score="6",
                pair2_score="2",
            )
        )

        assert result.pair1_score == "6"
        mock_match_repo.save.assert_awaited_once_with(match)

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

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchEditWindowExpiredError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    pair1_score="6",
                    pair2_score="2",
                )
            )

        mock_match_repo.save.assert_not_awaited()

    async def test_player_league_not_found_raises_league_not_found(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        mock_league_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token=None,
                    league_id="00000000-0000-0000-0000-000000000000",
                    match_id="00000000-0000-0000-0000-000000000001",
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_player_match_not_found_raises_match_not_found(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="any-token")
        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_default_window_seconds_is_3600(
        self, mock_league_repo: AsyncMock, mock_match_repo: AsyncMock
    ) -> None:
        # Constructed without an explicit window_seconds, the default
        # is 1 hour. A match older than that fails for a player.
        league = make_league(host_token="any-token")
        match = make_match(league.league_id, PairId.generate(), PairId.generate())
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=3700)

        mock_league_repo.get_by_id.return_value = league
        mock_match_repo.get_by_id.return_value = match
        use_case = EditMatchScoreUseCase(mock_league_repo, mock_match_repo)

        with pytest.raises(MatchEditWindowExpiredError) as exc:
            await use_case.execute(
                EditMatchScoreCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    pair1_score="7",
                    pair2_score="5",
                )
            )
        assert exc.value.window_seconds == 3600
