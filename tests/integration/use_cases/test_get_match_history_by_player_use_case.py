"""Integration tests for GetMatchHistoryByPlayerUseCase."""
from __future__ import annotations

from functools import partial

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.use_cases.get_match_history_by_player_use_case import (
    GetMatchHistoryByPlayerQuery,
    GetMatchHistoryByPlayerUseCase,
)
from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)
from tests.integration.conftest import _session_factory
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


def _use_case(session: AsyncSession) -> GetMatchHistoryByPlayerUseCase:
    return GetMatchHistoryByPlayerUseCase(
        SqlAlchemyLeagueRepository(session),
        SqlAlchemyMatchRepository(session),
    )


async def _submit_match(
    factory: async_sessionmaker[AsyncSession],
    league_id: str,
    team1: tuple[str, str],
    team2: tuple[str, str],
    team1_score: str = "6",
    team2_score: str = "3",
) -> str:
    result = await SubmitMatchResultUseCase(
        partial(SqlAlchemySubmitMatchResultUnitOfWork, factory)
    ).execute(
        SubmitMatchResultCommand(
            league_id=league_id,
            team1_nicknames=team1,
            team2_nicknames=team2,
            team1_score=team1_score,
            team2_score=team2_score,
        )
    )
    return result.match_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_returns_matches_for_player(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]

    async with _session_factory() as s:
        records = await _use_case(s).execute(
            GetMatchHistoryByPlayerQuery(
                league_id=str(league.league_id), player_name="alice"
            )
        )

    assert len(records) == 1
    assert records[0].match_id == match_id
    assert records[0].team1_score == "6"
    assert records[0].team2_score == "3"
    team1_nicks = {records[0].team1_player1_nickname, records[0].team1_player2_nickname}
    team2_nicks = {records[0].team2_player1_nickname, records[0].team2_player2_nickname}
    assert team1_nicks == {"alice", "bob"}
    assert team2_nicks == {"charlie", "diana"}


async def test_player_name_lookup_is_case_insensitive(
    persisted_league_with_match: dict,
) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]

    async with _session_factory() as s:
        records = await _use_case(s).execute(
            GetMatchHistoryByPlayerQuery(
                league_id=str(league.league_id), player_name="ALICE"
            )
        )

    assert len(records) == 1
    assert records[0].match_id == match_id


async def test_returns_only_matches_involving_player(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Alice's matches should not include a match between two other teams."""
    async with session_factory() as s:
        league = League.create(
            "Filter Test League",
            None,
            "tok",
            rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
        )
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()

    league_id = str(league.league_id)

    alice_match_id = await _submit_match(
        session_factory, league_id, ("alice", "bob"), ("charlie", "diana")
    )
    await _submit_match(
        session_factory, league_id, ("edgar", "frank"), ("george", "henry")
    )

    async with _session_factory() as s:
        records = await _use_case(s).execute(
            GetMatchHistoryByPlayerQuery(league_id=league_id, player_name="alice")
        )

    assert len(records) == 1
    assert records[0].match_id == alice_match_id


async def test_returns_multiple_matches_for_player(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as s:
        league = League.create(
            "Multi Match League",
            None,
            "tok",
            rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
        )
        await SqlAlchemyLeagueRepository(s).save(league)
        await s.commit()

    league_id = str(league.league_id)

    match1_id = await _submit_match(
        session_factory, league_id, ("alice", "bob"), ("charlie", "diana"), "6", "3"
    )
    match2_id = await _submit_match(
        session_factory, league_id, ("charlie", "diana"), ("alice", "bob"), "4", "6"
    )

    async with _session_factory() as s:
        records = await _use_case(s).execute(
            GetMatchHistoryByPlayerQuery(league_id=league_id, player_name="alice")
        )

    assert len(records) == 2
    returned_ids = {r.match_id for r in records}
    assert returned_ids == {match1_id, match2_id}


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await _use_case(session).execute(
            GetMatchHistoryByPlayerQuery(
                league_id="00000000-0000-0000-0000-000000000000",
                player_name="alice",
            )
        )


async def test_raises_for_unknown_player(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]

    async with _session_factory() as s:
        with pytest.raises(PlayerNotFoundError):
            await _use_case(s).execute(
                GetMatchHistoryByPlayerQuery(
                    league_id=str(league.league_id),
                    player_name="ghost_player",
                )
            )
