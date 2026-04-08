"""Unit tests for SubmitMatchResultUseCase."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.exceptions import (
    LeagueNotFoundError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
)
from tests.application.conftest import make_league


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
    uow.match_repo.exists_match_for_team_pair = AsyncMock(return_value=False)
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
                team1_nicknames=("alice", "bob"),
                team2_nicknames=("charlie", "diana"),
                team1_score="6",
                team2_score="3",
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
                    team1_nicknames=("alice", "bob"),
                    team2_nicknames=("charlie", "diana"),
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_same_player_in_team1_twice_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSingleTeamError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    team1_nicknames=("alice", "alice"),
                    team2_nicknames=("charlie", "diana"),
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_same_player_in_team2_twice_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSingleTeamError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    team1_nicknames=("alice", "bob"),
                    team2_nicknames=("charlie", "charlie"),
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_same_player_on_both_teams_raises(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerOnBothTeamsError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    team1_nicknames=("alice", "bob"),
                    team2_nicknames=("alice", "charlie"),
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_nicknames_normalised_before_validation(self) -> None:
        league = make_league()
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(SamePlayerWithinSingleTeamError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    team1_nicknames=("Alice", "ALICE"),
                    team2_nicknames=("charlie", "diana"),
                    team1_score="6",
                    team2_score="3",
                )
            )

    async def test_registers_new_players_and_commits(self) -> None:
        league = make_league()
        factory, uow = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                team1_nicknames=("alice", "bob"),
                team2_nicknames=("charlie", "diana"),
                team1_score="6",
                team2_score="3",
            )
        )

        uow.league_repo.save.assert_awaited_once()
        uow.match_repo.save.assert_awaited_once()
        uow.commit.assert_awaited_once()

    async def test_player_on_different_team_raises_team_conflict(self) -> None:
        league = make_league()
        league.register_players_and_team("alice", "bob")
        factory, _ = _make_uow_factory(league)
        use_case = SubmitMatchResultUseCase(factory)

        with pytest.raises(TeamConflictError):
            await use_case.execute(
                SubmitMatchResultCommand(
                    league_id=str(league.league_id),
                    team1_nicknames=("alice", "charlie"),
                    team2_nicknames=("diana", "eve"),
                    team1_score="6",
                    team2_score="3",
                )
            )
