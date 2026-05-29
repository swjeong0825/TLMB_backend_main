"""Integration tests for SubmitMatchResultUseCase."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from functools import partial
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import (
    DuplicatePairMatchupMatchError,
    LeagueNotFoundError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
    PairConflictError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from app.infrastructure.persistence.models.orm_models import MatchORM
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS


def _use_case(sf: async_sessionmaker) -> SubmitMatchResultUseCase:
    return SubmitMatchResultUseCase(partial(SqlAlchemySubmitMatchResultUnitOfWork, sf))


async def _create_league(sf: async_sessionmaker, title: str = "Test", token: str = "tok") -> League:
    async with sf() as s:
        league = League.create(
            title,
            None,
            token,
            host_email="host@example.com",
            rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
        )
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()
    return league


def _rules(pair_matchup_idempotency: str) -> LeagueRules:
    return LeagueRules.from_dict(
        {
            "version": 8,
            "pair_matchup_idempotency": pair_matchup_idempotency,
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
    )


async def _create_league_with_rules(
    sf: async_sessionmaker,
    title: str,
    rules: LeagueRules,
    league_timezone: str = "America/Los_Angeles",
) -> League:
    async with sf() as s:
        league = League.create(
            title,
            None,
            "tok",
            host_email="host@example.com",
            league_timezone=league_timezone,
            rules=rules,
        )
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()
    return league


async def _set_match_created_at(
    sf: async_sessionmaker, match_id: str, created_at: datetime
) -> None:
    async with sf() as s:
        await s.execute(
            update(MatchORM)
            .where(MatchORM.match_id == UUID(match_id))
            .values(created_at=created_at, updated_at=created_at)
        )
        await s.commit()


async def test_creates_players_pairs_and_match(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    result = await _use_case(session_factory).execute(
        SubmitMatchResultCommand(
            league_id=str(league.league_id),
            pair1_nicknames=("alice", "bob"),
            pair2_nicknames=("charlie", "diana"),
            pair1_score="6",
            pair2_score="3",
        )
    )

    assert result.match_id
    async with session_factory() as s:
        saved_league = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(saved_league.players) == 4
        assert len(saved_league.pairs) == 2
        assert saved_league.latest_match_date == result.created_at.astimezone(
            ZoneInfo(saved_league.league_timezone.value)
        ).date()

        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)
        assert len(matches) == 1
        assert matches[0].set_score.pair1_score == "6"
        assert matches[0].set_score.pair2_score == "3"


async def test_reuses_existing_pair_on_rematch(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        pair1_nicknames=("alice", "bob"),
        pair2_nicknames=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    await use_case.execute(cmd)
    await use_case.execute(cmd)

    async with session_factory() as s:
        saved = await SqlAlchemyLeagueRepository(s).get_by_id(league.league_id)
        assert len(saved.players) == 4   # no duplicates
        assert len(saved.pairs) == 2     # no duplicate pairs

        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)
        assert len(matches) == 2


async def test_raises_for_unknown_league(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(LeagueNotFoundError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id="00000000-0000-0000-0000-000000000000",
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )


async def test_raises_for_same_player_within_pair(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    with pytest.raises(SamePlayerWithinSinglePairError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "alice"),
                pair2_nicknames=("charlie", "diana"),
                pair1_score="6",
                pair2_score="3",
            )
        )


async def test_raises_for_same_player_on_both_pairs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    with pytest.raises(SamePlayerOnBothPairsError):
        await _use_case(session_factory).execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "bob"),
                pair2_nicknames=("alice", "charlie"),
                pair1_score="6",
                pair2_score="3",
            )
        )


async def test_raises_when_player_already_in_another_pair(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league(session_factory)
    use_case = _use_case(session_factory)

    # Register alice+bob as a pair
    await use_case.execute(
        SubmitMatchResultCommand(
            league_id=str(league.league_id),
            pair1_nicknames=("alice", "bob"),
            pair2_nicknames=("charlie", "diana"),
            pair1_score="6",
            pair2_score="3",
        )
    )

    # Try to pair alice with eve in a different pair
    with pytest.raises(PairConflictError):
        await use_case.execute(
            SubmitMatchResultCommand(
                league_id=str(league.league_id),
                pair1_nicknames=("alice", "eve"),
                pair2_nicknames=("frank", "grace"),
                pair1_score="6",
                pair2_score="3",
            )
        )


async def test_raises_duplicate_pair_matchup_when_once_per_league(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league_with_rules(
        session_factory,
        "Dup Pair League",
        _rules("once_per_league"),
    )

    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        pair1_nicknames=("alice", "bob"),
        pair2_nicknames=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )
    await use_case.execute(cmd)
    with pytest.raises(DuplicatePairMatchupMatchError):
        await use_case.execute(cmd)


async def test_raises_duplicate_pair_matchup_when_once_per_day_and_same_local_day(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league_with_rules(
        session_factory,
        "Daily Pair League",
        _rules("once_per_day"),
    )
    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        pair1_nicknames=("alice", "bob"),
        pair2_nicknames=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    await use_case.execute(cmd)
    with pytest.raises(DuplicatePairMatchupMatchError):
        await use_case.execute(cmd)


async def test_allows_same_pair_when_once_per_day_and_prior_local_day(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league_with_rules(
        session_factory,
        "Daily Reopen League",
        _rules("once_per_day"),
        league_timezone="America/Los_Angeles",
    )
    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        pair1_nicknames=("alice", "bob"),
        pair2_nicknames=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    first = await use_case.execute(cmd)
    league_tz = ZoneInfo("America/Los_Angeles")
    previous_local_day = (
        datetime.now(timezone.utc).astimezone(league_tz).date()
        - timedelta(days=1)
    )
    previous_created_at = datetime.combine(
        previous_local_day, time(12, 0), tzinfo=league_tz
    ).astimezone(timezone.utc)
    await _set_match_created_at(session_factory, first.match_id, previous_created_at)

    second = await use_case.execute(cmd)

    assert second.match_id != first.match_id


async def test_once_per_day_uses_league_local_day_not_rolling_24_hours(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    league = await _create_league_with_rules(
        session_factory,
        "Local Midnight League",
        _rules("once_per_day"),
        league_timezone="America/Los_Angeles",
    )
    use_case = _use_case(session_factory)
    cmd = SubmitMatchResultCommand(
        league_id=str(league.league_id),
        pair1_nicknames=("alice", "bob"),
        pair2_nicknames=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    first = await use_case.execute(cmd)
    league_tz = ZoneInfo("America/Los_Angeles")
    previous_local_day = (
        datetime.now(timezone.utc).astimezone(league_tz).date()
        - timedelta(days=1)
    )
    previous_created_at = datetime.combine(
        previous_local_day, time(23, 59), tzinfo=league_tz
    ).astimezone(timezone.utc)
    await _set_match_created_at(session_factory, first.match_id, previous_created_at)

    second = await use_case.execute(cmd)

    assert second.match_id != first.match_id
