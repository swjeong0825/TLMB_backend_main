"""Unit tests for singles match write use cases."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.delete_singles_match_use_case import (
    DeleteSinglesMatchCommand,
    DeleteSinglesMatchUseCase,
)
from app.application.use_cases.edit_singles_match_score_use_case import (
    EditSinglesMatchScoreCommand,
    EditSinglesMatchScoreUseCase,
)
from app.application.use_cases.submit_singles_match_result_use_case import (
    SubmitSinglesMatchResultCommand,
    SubmitSinglesMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchDeleteWindowExpiredError,
    MatchEditWindowExpiredError,
    MatchNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothSidesError,
    UnauthorizedError,
)
from tests.application.conftest import make_league


def _league_require_roster() -> League:
    rules = LeagueRules.from_dict(
        {
            "version": 8,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": False,
        }
    )
    return League.create(
        title="Roster-Only League",
        description=None,
        host_token="test-host-token",
        host_email="host@example.com",
        rules=rules,
    )


def _make_singles_match(
    league_id: LeagueId,
    player1_id: PlayerId | None = None,
    player2_id: PlayerId | None = None,
) -> SinglesMatch:
    return SinglesMatch.create(
        league_id=league_id,
        player1_id=player1_id or PlayerId.generate(),
        player2_id=player2_id or PlayerId.generate(),
        set_score=SetScore("6", "3"),
    )


def _make_submit_uow_factory(league: League | None):
    uow = MagicMock()
    uow.league_repo = AsyncMock()
    uow.league_repo.get_by_id_with_lock = AsyncMock(return_value=league)
    uow.league_repo.save = AsyncMock(return_value=None)
    uow.singles_match_repo = AsyncMock()
    uow.singles_match_repo.save = AsyncMock(return_value=None)
    uow.commit = AsyncMock(return_value=None)
    uow.rollback = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _ctx() -> AsyncGenerator:
        yield uow

    class _Factory:
        def __call__(self):
            return _ctx()

    return _Factory(), uow


class TestSubmitSinglesMatchResultUseCase:
    async def test_happy_path_registers_players_without_pairing_and_commits(self) -> None:
        league = make_league()
        factory, uow = _make_submit_uow_factory(league)
        use_case = SubmitSinglesMatchResultUseCase(factory)

        result = await use_case.execute(
            SubmitSinglesMatchResultCommand(
                league_id=str(league.league_id),
                player1_nickname="Alice",
                player2_nickname="Bob",
                player1_score="6",
                player2_score="3",
            )
        )

        assert result.match_id
        assert [p.canonical_nickname.value for p in league.players] == [
            "alice",
            "bob",
        ]
        assert league.pairs == []
        assert league.latest_match_date_single is not None
        assert league.latest_match_date is None
        assert uow.league_repo.save.await_count == 2
        uow.singles_match_repo.save.assert_awaited_once()
        uow.commit.assert_awaited_once()

    async def test_same_input_player_raises_before_uow(self) -> None:
        factory, uow = _make_submit_uow_factory(make_league())
        use_case = SubmitSinglesMatchResultUseCase(factory)

        with pytest.raises(SamePlayerOnBothSidesError):
            await use_case.execute(
                SubmitSinglesMatchResultCommand(
                    league_id="00000000-0000-0000-0000-000000000000",
                    player1_nickname="Alice",
                    player2_nickname=" ALICE ",
                    player1_score="6",
                    player2_score="3",
                )
            )

        uow.league_repo.get_by_id_with_lock.assert_not_awaited()

    async def test_aliases_resolving_to_same_player_raise(self) -> None:
        league = make_league()
        alice = league.add_players(["alice"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        factory, _ = _make_submit_uow_factory(league)
        use_case = SubmitSinglesMatchResultUseCase(factory)

        with pytest.raises(SamePlayerOnBothSidesError):
            await use_case.execute(
                SubmitSinglesMatchResultCommand(
                    league_id=str(league.league_id),
                    player1_nickname="ali",
                    player2_nickname="alice",
                    player1_score="6",
                    player2_score="3",
                )
            )

    async def test_roster_only_league_rejects_missing_player(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice"])
        factory, _ = _make_submit_uow_factory(league)
        use_case = SubmitSinglesMatchResultUseCase(factory)

        with pytest.raises(RosterMembershipRequiredError):
            await use_case.execute(
                SubmitSinglesMatchResultCommand(
                    league_id=str(league.league_id),
                    player1_nickname="alice",
                    player2_nickname="bob",
                    player1_score="6",
                    player2_score="3",
                )
            )

    async def test_league_not_found_raises(self) -> None:
        factory, _ = _make_submit_uow_factory(None)
        use_case = SubmitSinglesMatchResultUseCase(factory)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                SubmitSinglesMatchResultCommand(
                    league_id="00000000-0000-0000-0000-000000000000",
                    player1_nickname="alice",
                    player2_nickname="bob",
                    player1_score="6",
                    player2_score="3",
                )
            )


class TestEditSinglesMatchScoreUseCase:
    def _use_case(
        self,
        league_repo: AsyncMock,
        singles_match_repo: AsyncMock,
        window_seconds: int = 3600,
    ) -> EditSinglesMatchScoreUseCase:
        return EditSinglesMatchScoreUseCase(
            league_repo, singles_match_repo, window_seconds=window_seconds
        )

    async def test_player_inside_window_updates_score(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = _make_singles_match(league.league_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=60)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = match

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo)

        result = await use_case.execute(
            EditSinglesMatchScoreCommand(
                host_token=None,
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                player1_score="7",
                player2_score="5",
            )
        )

        assert result.player1_score == "7"
        assert result.player2_score == "5"
        singles_match_repo.save.assert_awaited_once_with(match)

    async def test_admin_bypasses_window(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = _make_singles_match(league.league_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = match

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo, 60)

        result = await use_case.execute(
            EditSinglesMatchScoreCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
                player1_score="4",
                player2_score="6",
            )
        )

        assert result.player1_score == "4"
        singles_match_repo.save.assert_awaited_once_with(match)

    async def test_player_outside_window_raises(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        match = _make_singles_match(league.league_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=7200)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = match

        mock_league_repo.get_by_id.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo, 3600)

        with pytest.raises(MatchEditWindowExpiredError):
            await use_case.execute(
                EditSinglesMatchScoreCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                    player1_score="4",
                    player2_score="6",
                )
            )

        singles_match_repo.save.assert_not_awaited()

    async def test_wrong_host_token_raises(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id.return_value = league
        singles_match_repo = AsyncMock()
        use_case = self._use_case(mock_league_repo, singles_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                EditSinglesMatchScoreCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    player1_score="4",
                    player2_score="6",
                )
            )

        singles_match_repo.get_by_id.assert_not_awaited()

    async def test_match_not_found_raises(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="valid-token")
        mock_league_repo.get_by_id.return_value = league
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = None
        use_case = self._use_case(mock_league_repo, singles_match_repo)

        with pytest.raises(MatchNotFoundError):
            await use_case.execute(
                EditSinglesMatchScoreCommand(
                    host_token="valid-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                    player1_score="4",
                    player2_score="6",
                )
            )


class TestDeleteSinglesMatchUseCase:
    def _use_case(
        self,
        league_repo: AsyncMock,
        singles_match_repo: AsyncMock,
        window_seconds: int = 600,
    ) -> DeleteSinglesMatchUseCase:
        return DeleteSinglesMatchUseCase(
            league_repo, singles_match_repo, window_seconds=window_seconds
        )

    async def test_deletes_and_recomputes_latest_date(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        deleted_match = _make_singles_match(league.league_id)
        remaining_match = _make_singles_match(league.league_id)
        remaining_match.created_at = datetime(2026, 5, 24, 18, 0, tzinfo=timezone.utc)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = deleted_match
        singles_match_repo.get_latest_by_league.return_value = remaining_match

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo)

        await use_case.execute(
            DeleteSinglesMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(deleted_match.match_id),
            )
        )

        singles_match_repo.delete.assert_awaited_once_with(
            deleted_match.match_id, league.league_id
        )
        assert league.latest_match_date_single == date(2026, 5, 24)
        mock_league_repo.save.assert_awaited_once_with(league)

    async def test_player_outside_window_raises(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league()
        match = _make_singles_match(league.league_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(seconds=1200)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = match

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo, 600)

        with pytest.raises(MatchDeleteWindowExpiredError):
            await use_case.execute(
                DeleteSinglesMatchCommand(
                    host_token=None,
                    league_id=str(league.league_id),
                    match_id=str(match.match_id),
                )
            )

        singles_match_repo.delete.assert_not_awaited()

    async def test_admin_bypasses_window(
        self, mock_league_repo: AsyncMock
    ) -> None:
        league = make_league(host_token="valid-token")
        match = _make_singles_match(league.league_id)
        match.created_at = datetime.now(timezone.utc) - timedelta(days=30)
        singles_match_repo = AsyncMock()
        singles_match_repo.get_by_id.return_value = match
        singles_match_repo.get_latest_by_league.return_value = None

        mock_league_repo.get_by_id_with_lock.return_value = league
        use_case = self._use_case(mock_league_repo, singles_match_repo, 60)

        await use_case.execute(
            DeleteSinglesMatchCommand(
                host_token="valid-token",
                league_id=str(league.league_id),
                match_id=str(match.match_id),
            )
        )

        singles_match_repo.delete.assert_awaited_once()

    async def test_wrong_host_token_raises(self, mock_league_repo: AsyncMock) -> None:
        league = make_league(host_token="correct-token")
        mock_league_repo.get_by_id_with_lock.return_value = league
        singles_match_repo = AsyncMock()
        use_case = self._use_case(mock_league_repo, singles_match_repo)

        with pytest.raises(UnauthorizedError):
            await use_case.execute(
                DeleteSinglesMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id="00000000-0000-0000-0000-000000000001",
                )
            )

        singles_match_repo.get_by_id.assert_not_awaited()

