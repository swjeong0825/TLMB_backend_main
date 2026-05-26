"""Integration tests for SqlAlchemyMatchRepository."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from app.infrastructure.persistence.models.orm_models import MatchORM
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_league_with_teams(
    session: AsyncSession,
) -> tuple[League, str, str]:
    """Persist a league with two teams; return (league, team1_id_str, team2_id_str)."""
    league = League.create(
        "Match Test League",
        None,
        "seed-token",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
    )
    _, team1 = league.register_players_and_team("alice", "bob")
    _, team2 = league.register_players_and_team("charlie", "diana")
    repo = SqlAlchemyLeagueRepository(session)
    await repo.save(league)
    await session.commit()
    return league, str(team1.team_id.value), str(team2.team_id.value)


def _make_match(league: League, t1_id_str: str, t2_id_str: str, t1_score: str = "6", t2_score: str = "3") -> Match:
    from app.domain.aggregates.league.value_objects import TeamId
    return Match.create(
        league.league_id,
        TeamId.from_str(t1_id_str),
        TeamId.from_str(t2_id_str),
        SetScore(t1_score, t2_score),
    )


async def _set_match_created_at(
    session: AsyncSession, match_id: str, created_at: datetime
) -> None:
    await session.execute(
        update(MatchORM)
        .where(MatchORM.match_id == UUID(match_id))
        .values(created_at=created_at, updated_at=created_at)
    )


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


async def test_get_by_id_returns_none_when_not_found(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)

    result = await repo.get_by_id(MatchId.generate(), league.league_id)

    assert result is None


async def test_get_by_id_returns_none_for_wrong_league(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    match = _make_match(league, t1, t2)
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    result = await repo.get_by_id(match.match_id, LeagueId.generate())

    assert result is None


async def test_save_and_get_by_id_round_trip(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    match = _make_match(league, t1, t2, "6", "4")
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(match.match_id, league.league_id)

    assert found is not None
    assert str(found.match_id.value) == str(match.match_id.value)
    assert found.set_score.team1_score == "6"
    assert found.set_score.team2_score == "4"


async def test_save_populates_created_at_on_aggregate(session: AsyncSession) -> None:
    """`save` flushes so the DB `server_default=now()` populates
    `created_at` and the in-memory aggregate observes it. The use case
    needs this to return an authoritative timestamp to the API layer
    (frontend uses it for the player-edit window math)."""
    league, t1, t2 = await _seed_league_with_teams(session)
    match = _make_match(league, t1, t2, "6", "4")
    assert match.created_at is None  # fresh aggregate has no timestamp

    repo = SqlAlchemyMatchRepository(session)
    await repo.save(match)

    assert match.created_at is not None


# ---------------------------------------------------------------------------
# get_all_by_league
# ---------------------------------------------------------------------------


async def test_get_all_by_league_returns_empty_when_no_matches(session: AsyncSession) -> None:
    league, _, _ = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)

    matches = await repo.get_all_by_league(league.league_id)

    assert matches == []


async def test_get_all_by_league_returns_all_matches(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(_make_match(league, t1, t2, "6", "3"))
    await repo.save(_make_match(league, t1, t2, "7", "5"))
    await session.commit()
    session.expire_all()

    matches = await repo.get_all_by_league(league.league_id)

    assert len(matches) == 2


async def test_get_all_by_league_does_not_return_other_leagues_matches(session: AsyncSession) -> None:
    league1, t1, t2 = await _seed_league_with_teams(session)

    league2 = League.create(
        "Other League",
        None,
        "other-token",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
    )
    _, l2_t1 = league2.register_players_and_team("eve", "frank")
    _, l2_t2 = league2.register_players_and_team("grace", "harry")
    await SqlAlchemyLeagueRepository(session).save(league2)
    await session.commit()

    repo = SqlAlchemyMatchRepository(session)
    await repo.save(_make_match(league1, t1, t2))
    await repo.save(_make_match(league2, str(l2_t1.team_id.value), str(l2_t2.team_id.value)))
    await session.commit()
    session.expire_all()

    matches = await repo.get_all_by_league(league1.league_id)
    assert len(matches) == 1


async def test_get_all_by_league_respects_created_at_bounds(
    session: AsyncSession,
) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    older = _make_match(league, t1, t2, "6", "3")
    newer = _make_match(league, t1, t2, "7", "5")
    await repo.save(older)
    await repo.save(newer)
    await session.commit()
    await _set_match_created_at(
        session, str(older.match_id.value), datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    )
    await _set_match_created_at(
        session, str(newer.match_id.value), datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    )
    await session.commit()

    matches = await repo.get_all_by_league(
        league.league_id,
        start_at=datetime(2026, 5, 24, 0, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 5, 25, 0, 0, tzinfo=timezone.utc),
    )

    assert [m.match_id for m in matches] == [newer.match_id]


async def test_get_latest_by_league_returns_newest_match(
    session: AsyncSession,
) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    older = _make_match(league, t1, t2, "6", "3")
    newer = _make_match(league, t1, t2, "7", "5")
    await repo.save(older)
    await repo.save(newer)
    await session.commit()
    await _set_match_created_at(
        session, str(older.match_id.value), datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc)
    )
    await _set_match_created_at(
        session, str(newer.match_id.value), datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
    )
    await session.commit()

    latest = await repo.get_latest_by_league(league.league_id)

    assert latest is not None
    assert latest.match_id == newer.match_id


# ---------------------------------------------------------------------------
# has_matches_for_team
# ---------------------------------------------------------------------------


async def test_has_matches_for_team_returns_true_when_team_played(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(_make_match(league, t1, t2))
    await session.commit()

    from app.domain.aggregates.league.value_objects import TeamId
    result = await repo.has_matches_for_team(TeamId.from_str(t1), league.league_id)
    assert result is True


async def test_has_matches_for_team_returns_false_when_no_matches(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)

    from app.domain.aggregates.league.value_objects import TeamId
    result = await repo.has_matches_for_team(TeamId.from_str(t1), league.league_id)
    assert result is False


# ---------------------------------------------------------------------------
# exists_match_for_team_pair
# ---------------------------------------------------------------------------


async def test_exists_match_for_team_pair_true_either_orientation(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(_make_match(league, t1, t2))
    await session.commit()

    from app.domain.aggregates.league.value_objects import TeamId

    t1id, t2id = TeamId.from_str(t1), TeamId.from_str(t2)
    assert await repo.exists_match_for_team_pair(league.league_id, t1id, t2id)
    assert await repo.exists_match_for_team_pair(league.league_id, t2id, t1id)


async def test_exists_match_for_team_pair_false_when_no_match(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)

    from app.domain.aggregates.league.value_objects import TeamId

    assert not await repo.exists_match_for_team_pair(
        league.league_id, TeamId.from_str(t1), TeamId.from_str(t2)
    )


async def test_exists_match_for_team_pair_between_respects_time_window(
    session: AsyncSession,
) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    repo = SqlAlchemyMatchRepository(session)
    match = _make_match(league, t1, t2)
    await repo.save(match)
    await session.commit()

    from app.domain.aggregates.league.value_objects import TeamId

    created_at = match.created_at or datetime.now(timezone.utc)
    assert await repo.exists_match_for_team_pair_between(
        league.league_id,
        TeamId.from_str(t2),
        TeamId.from_str(t1),
        created_at - timedelta(minutes=1),
        created_at + timedelta(minutes=1),
    )
    assert not await repo.exists_match_for_team_pair_between(
        league.league_id,
        TeamId.from_str(t1),
        TeamId.from_str(t2),
        created_at + timedelta(minutes=1),
        created_at + timedelta(minutes=2),
    )


# ---------------------------------------------------------------------------
# save – update path
# ---------------------------------------------------------------------------


async def test_save_updates_existing_match_score(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    match = _make_match(league, t1, t2, "6", "3")
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    match.edit_score(SetScore("2", "6"))
    await repo.save(match)
    await session.commit()
    session.expire_all()

    updated = await repo.get_by_id(match.match_id, league.league_id)
    assert updated.set_score.team1_score == "2"
    assert updated.set_score.team2_score == "6"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


async def test_delete_removes_match_from_db(session: AsyncSession) -> None:
    league, t1, t2 = await _seed_league_with_teams(session)
    match = _make_match(league, t1, t2)
    repo = SqlAlchemyMatchRepository(session)
    await repo.save(match)
    await session.commit()
    session.expire_all()

    await repo.delete(match.match_id, league.league_id)
    await session.commit()
    session.expire_all()

    assert await repo.get_by_id(match.match_id, league.league_id) is None
