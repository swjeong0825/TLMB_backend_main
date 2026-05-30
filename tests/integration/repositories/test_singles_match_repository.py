"""Integration tests for SqlAlchemySinglesMatchRepository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import PlayerId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId
from app.infrastructure.persistence.models.orm_models import SinglesMatchORM
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.singles_match_repository import (
    SqlAlchemySinglesMatchRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS


async def _seed_league_with_players(
    session: AsyncSession,
) -> tuple[League, PlayerId, PlayerId, PlayerId]:
    league = League.create(
        "Singles Match Test League",
        None,
        "seed-token",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
    )
    alice, bob, charlie = league.add_players(["alice", "bob", "charlie"])
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()
    return league, alice.player_id, bob.player_id, charlie.player_id


def _make_match(
    league: League,
    player1_id: PlayerId,
    player2_id: PlayerId,
    p1_score: str = "6",
    p2_score: str = "3",
) -> SinglesMatch:
    return SinglesMatch.create(
        league.league_id,
        player1_id,
        player2_id,
        SetScore(p1_score, p2_score),
    )


async def _set_created_at(
    session: AsyncSession, match_id: SinglesMatchId, created_at: datetime
) -> None:
    await session.execute(
        update(SinglesMatchORM)
        .where(SinglesMatchORM.match_id == UUID(str(match_id)))
        .values(created_at=created_at, updated_at=created_at)
    )


async def test_get_by_id_returns_none_when_not_found(session: AsyncSession) -> None:
    league, _, _, _ = await _seed_league_with_players(session)
    repo = SqlAlchemySinglesMatchRepository(session)

    result = await repo.get_by_id(SinglesMatchId.generate(), league.league_id)

    assert result is None


async def test_save_and_get_by_id_round_trip(session: AsyncSession) -> None:
    league, alice_id, bob_id, _ = await _seed_league_with_players(session)
    match = _make_match(league, alice_id, bob_id, "7", "5")
    repo = SqlAlchemySinglesMatchRepository(session)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(match.match_id, league.league_id)

    assert found is not None
    assert found.match_id == match.match_id
    assert found.player1_id == alice_id
    assert found.player2_id == bob_id
    assert found.set_score.pair1_score == "7"
    assert found.set_score.pair2_score == "5"


async def test_save_populates_created_at_on_aggregate(session: AsyncSession) -> None:
    league, alice_id, bob_id, _ = await _seed_league_with_players(session)
    match = _make_match(league, alice_id, bob_id)
    repo = SqlAlchemySinglesMatchRepository(session)

    await repo.save(match)

    assert match.created_at is not None


async def test_get_all_by_league_and_latest_use_created_at_order(
    session: AsyncSession,
) -> None:
    league, alice_id, bob_id, charlie_id = await _seed_league_with_players(session)
    repo = SqlAlchemySinglesMatchRepository(session)
    older = _make_match(league, alice_id, bob_id, "6", "4")
    newer = _make_match(league, alice_id, charlie_id, "7", "5")
    await repo.save(older)
    await repo.save(newer)
    await session.commit()
    await _set_created_at(
        session, older.match_id, datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    )
    await _set_created_at(
        session, newer.match_id, datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    )
    await session.commit()
    session.expire_all()

    matches = await repo.get_all_by_league(league.league_id)
    latest = await repo.get_latest_by_league(league.league_id)

    assert [m.match_id for m in matches] == [newer.match_id, older.match_id]
    assert latest is not None
    assert latest.match_id == newer.match_id


async def test_get_all_by_player_matches_either_side(session: AsyncSession) -> None:
    league, alice_id, bob_id, charlie_id = await _seed_league_with_players(session)
    repo = SqlAlchemySinglesMatchRepository(session)
    match1 = _make_match(league, alice_id, bob_id)
    match2 = _make_match(league, charlie_id, alice_id)
    await repo.save(match1)
    await repo.save(match2)
    await session.commit()
    session.expire_all()

    matches = await repo.get_all_by_player(league.league_id, alice_id)

    assert {m.match_id for m in matches} == {match1.match_id, match2.match_id}


async def test_exists_match_for_player_matchup_matches_either_side(
    session: AsyncSession,
) -> None:
    league, alice_id, bob_id, charlie_id = await _seed_league_with_players(session)
    repo = SqlAlchemySinglesMatchRepository(session)
    match = _make_match(league, alice_id, bob_id)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    assert await repo.exists_match_for_player_matchup(
        league.league_id, alice_id, bob_id
    )
    assert await repo.exists_match_for_player_matchup(
        league.league_id, bob_id, alice_id
    )
    assert not await repo.exists_match_for_player_matchup(
        league.league_id, alice_id, charlie_id
    )


async def test_exists_match_for_player_matchup_between_respects_window(
    session: AsyncSession,
) -> None:
    league, alice_id, bob_id, _ = await _seed_league_with_players(session)
    repo = SqlAlchemySinglesMatchRepository(session)
    match = _make_match(league, alice_id, bob_id)
    created_at = datetime(2026, 5, 30, 15, 0, tzinfo=timezone.utc)
    await repo.save(match)
    await session.commit()
    await _set_created_at(session, match.match_id, created_at)
    await session.commit()
    session.expire_all()

    assert await repo.exists_match_for_player_matchup_between(
        league.league_id,
        bob_id,
        alice_id,
        created_at - timedelta(hours=1),
        created_at + timedelta(hours=1),
    )
    assert not await repo.exists_match_for_player_matchup_between(
        league.league_id,
        alice_id,
        bob_id,
        created_at - timedelta(hours=3),
        created_at - timedelta(hours=1),
    )


async def test_save_updates_existing_score(session: AsyncSession) -> None:
    league, alice_id, bob_id, _ = await _seed_league_with_players(session)
    match = _make_match(league, alice_id, bob_id)
    repo = SqlAlchemySinglesMatchRepository(session)
    await repo.save(match)
    await session.commit()

    match.edit_score(SetScore("4", "6"))
    await repo.save(match)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(match.match_id, league.league_id)
    assert found is not None
    assert found.set_score.pair1_score == "4"
    assert found.set_score.pair2_score == "6"


async def test_delete_removes_match(session: AsyncSession) -> None:
    league, alice_id, bob_id, _ = await _seed_league_with_players(session)
    match = _make_match(league, alice_id, bob_id)
    repo = SqlAlchemySinglesMatchRepository(session)
    await repo.save(match)
    await session.commit()

    await repo.delete(match.match_id, league.league_id)
    await session.commit()

    assert await repo.get_by_id(match.match_id, league.league_id) is None
