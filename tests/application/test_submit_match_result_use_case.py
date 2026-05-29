"""Unit tests for SubmitMatchResultUseCase."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import (
    DuplicatePairMatchupMatchError,
    LeagueNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
    PairConflictError,
)
from tests.application.conftest import make_league


def _league_require_roster() -> League:
    """League with v6 `auto_register_players_on_match=False` —
    only pre-registered roster members can submit matches."""
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


def _league_with_pair_matchup_idempotency(value: str) -> League:
    rules = LeagueRules.from_dict(
        {
            "version": 8,
            "pair_matchup_idempotency": value,
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
    )
    return League.create(
        title="Pair Rule League",
        description=None,
        host_token="test-host-token",
        host_email="host@example.com",
        rules=rules,
    )


def _league_otpp_false() -> League:
    rules = LeagueRules.from_dict(
        {
            "version": 8,
            "pair_matchup_idempotency": "none",
            "one_pair_per_player": False,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
    )
    return League.create(
        title="Alias League",
        description=None,
        host_token="test-host-token",
        host_email="host@example.com",
        rules=rules,
    )


# ---------------------------------------------------------------------------
# UoW mock helper
# ---------------------------------------------------------------------------


def _make_uow_factory(league=None):
    """Build a UoW factory whose context manager exposes mock repos."""
    uow = MagicMock()
    uow.league_repo = AsyncMock()
    uow.league_repo.get_by_id_with_lock = AsyncMock(return_value=league)
    uow.league_repo.save = AsyncMock(return_value=None)
    uow.match_repo = AsyncMock()
    uow.match_repo.exists_match_for_pair_matchup = AsyncMock(return_value=False)
    uow.match_repo.exists_match_for_pair_matchup_between = AsyncMock(return_value=False)
    uow.match_repo.get_latest_by_league = AsyncMock(return_value=None)
    uow.match_repo.save = AsyncMock(return_value=None)
    uow.commit = AsyncMock(return_value=None)
    uow.rollback = AsyncMock(return_value=None)

    @asynccontextmanager
    async def _ctx() -> AsyncGenerator:
        yield uow

    class _Factory:
        def __call__(self):
            return _ctx()

    return _Factory(), uow


class TestSubmitMatchResultUseCase:
    async def test_happy_path_returns_match_id(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        result = await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )

        assert result.match_id is not None
        assert len(result.match_id) > 0

    async def test_league_not_found_raises(self) -> None:
        factory, _ = _make_uow_factory(league=None)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(LeagueNotFoundError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id="00000000-0000-0000-0000-000000000000",
                    pair1_nicknames=("alice", "bob"),
                    pair2_nicknames=("charlie", "diana"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_same_player_in_pair1_twice_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSinglePairError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "alice"),
                    pair2_nicknames=("charlie", "diana"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_same_player_in_pair2_twice_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSinglePairError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "bob"),
                    pair2_nicknames=("charlie", "charlie"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_same_player_on_both_pairs_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerOnBothPairsError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "bob"),
                    pair2_nicknames=("alice", "charlie"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_same_player_on_both_pairs_via_alias_raises(self) -> None:
        league = _league_otpp_false()
        alice = league.add_players(["alice", "bob", "charlie"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerOnBothPairsError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("ali", "bob"),
                    pair2_nicknames=("alice", "charlie"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_nicknames_normalised_before_validation(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSinglePairError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("Alice", "ALICE"),
                    pair2_nicknames=("charlie", "diana"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

    async def test_registers_new_players_and_commits(self) -> None:
        league = make_league()
        factory, uow = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )

        assert uow.league_repo.save.await_count == 2
        uow.match_repo.save.assert_awaited_once()
        uow.commit.assert_awaited_once()
        assert league.latest_match_date is not None

    async def test_match_submission_with_alias_reuses_existing_player(self) -> None:
        league = make_league()
        alice = league.add_players(["alice"])[0]
        league.add_alias_to_player(str(alice.player_id.value), "ali")
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("ali", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )

        alice_rows = [p for p in league.players if p.player_id == alice.player_id]
        assert len(alice_rows) == 1
        assert {p.nickname.value for p in league.players} == {
            "alice",
            "bob",
            "charlie",
            "diana",
        }

    async def test_player_on_different_pair_raises_pair_conflict(self) -> None:
        league = make_league()
        league.register_players_and_pair("alice", "bob")
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(PairConflictError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "charlie"),
                    pair2_nicknames=("diana", "eve"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )


# ---------------------------------------------------------------------------
# v8: pair matchup idempotency
# ---------------------------------------------------------------------------


class TestSubmitMatchResultPairMatchupIdempotency:
    async def test_once_per_day_checks_pair_matchup_with_calendar_day_bounds(self) -> None:
        league = _league_with_pair_matchup_idempotency("once_per_day")
        factory, uow = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )

        uow.match_repo.exists_match_for_pair_matchup.assert_not_awaited()
        uow.match_repo.exists_match_for_pair_matchup_between.assert_awaited_once()
        args = uow.match_repo.exists_match_for_pair_matchup_between.await_args.args
        assert args[0] == league.league_id
        assert args[3].tzinfo == timezone.utc
        assert args[4].tzinfo == timezone.utc
        assert args[3] < args[4]

    async def test_once_per_day_duplicate_raises(self) -> None:
        league = _league_with_pair_matchup_idempotency("once_per_day")
        factory, uow = _make_uow_factory(league)
        uow.match_repo.exists_match_for_pair_matchup_between.return_value = True
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(DuplicatePairMatchupMatchError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "bob"),
                    pair2_nicknames=("charlie", "diana"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

        uow.league_repo.save.assert_not_awaited()
        uow.match_repo.save.assert_not_awaited()

    async def test_once_per_league_still_uses_global_pair_check(self) -> None:
        league = _league_with_pair_matchup_idempotency("once_per_league")
        factory, uow = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )

        uow.match_repo.exists_match_for_pair_matchup.assert_awaited_once()
        uow.match_repo.exists_match_for_pair_matchup_between.assert_not_awaited()


# ---------------------------------------------------------------------------
# v6: roster-membership gate via LeagueRules.auto_register_players_on_match
# ---------------------------------------------------------------------------


class TestSubmitMatchResultRosterGate:
    async def test_default_league_with_auto_register_true_does_not_check_roster(self) -> None:
        """Default leagues have auto_register_players_on_match=True; submission
        must succeed even though the roster is empty (today's UX preserved)."""
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        result = await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )
        assert result.match_id is not None

    async def test_flag_off_and_all_on_roster_succeeds(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob", "charlie", "diana"])
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        result = await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )
        assert result.match_id is not None

    async def test_flag_off_and_missing_nickname_raises_with_payload(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob"])
        factory, uow = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(RosterMembershipRequiredError) as exc:
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    pair1_nicknames=("alice", "bob"),
                    pair2_nicknames=("michael", "ryan"),
                    pair1_score="6",
                    pair2_score="3",
                )
            )

        assert exc.value.missing_nicknames == ["michael", "ryan"]
        uow.league_repo.save.assert_not_awaited()
        uow.match_repo.save.assert_not_awaited()

    async def test_flag_off_input_normalized_before_check(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob", "charlie", "diana"])
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        result = await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("ALICE", "Bob"),
                pair2_nicknames=("Charlie", "DIANA"),
                pair1_score="6",
                pair2_score="3",
            )
        )
        assert result.match_id is not None
