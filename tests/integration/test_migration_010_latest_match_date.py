"""Behavior test for alembic 010 (leagues.latest_match_date backfill).

The integration database is already at HEAD, so this executes the same
backfill statement the migration uses against fixture rows.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.infrastructure.persistence.models.orm_models import MatchORM
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


_BACKFILL_SQL = """
UPDATE leagues AS l
SET latest_match_date = latest.latest_match_date
FROM (
    SELECT
        m.league_id,
        MAX((m.created_at AT TIME ZONE l2.league_timezone)::date) AS latest_match_date
    FROM matches AS m
    JOIN leagues AS l2 ON l2.league_id = m.league_id
    GROUP BY m.league_id
) AS latest
WHERE l.league_id = latest.league_id
"""


async def _set_match_created_at(
    session: AsyncSession, match_id: str, created_at: datetime
) -> None:
    await session.execute(
        update(MatchORM)
        .where(MatchORM.match_id == UUID(match_id))
        .values(created_at=created_at, updated_at=created_at)
    )


async def test_backfill_sets_latest_match_date_from_league_local_date(
    session: AsyncSession,
) -> None:
    league = League.create(
        "Seoul Date Backfill",
        None,
        "fixture-host-token",
        host_email="host@example.com",
        league_timezone="Asia/Seoul",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
    )
    _, team1 = league.register_players_and_team("alice", "bob")
    _, team2 = league.register_players_and_team("charlie", "diana")
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()

    match_repo = SqlAlchemyMatchRepository(session)
    older = Match.create(
        league.league_id,
        TeamId(team1.team_id.value),
        TeamId(team2.team_id.value),
        SetScore("6", "3"),
    )
    newer = Match.create(
        league.league_id,
        TeamId(team1.team_id.value),
        TeamId(team2.team_id.value),
        SetScore("7", "5"),
    )
    await match_repo.save(older)
    await match_repo.save(newer)
    await session.commit()

    await _set_match_created_at(
        session,
        str(older.match_id.value),
        datetime(2026, 5, 24, 14, 30, tzinfo=timezone.utc),
    )
    await _set_match_created_at(
        session,
        str(newer.match_id.value),
        datetime(2026, 5, 24, 16, 30, tzinfo=timezone.utc),
    )
    await session.execute(
        text("UPDATE leagues SET latest_match_date = NULL WHERE league_id = :league_id"),
        {"league_id": league.league_id.value},
    )
    await session.commit()

    await session.execute(text(_BACKFILL_SQL))
    await session.commit()

    row = await session.execute(
        text("SELECT latest_match_date FROM leagues WHERE league_id = :league_id"),
        {"league_id": league.league_id.value},
    )

    assert row.scalar_one() == date(2026, 5, 25)


async def test_backfill_leaves_empty_league_latest_match_date_null(
    session: AsyncSession,
) -> None:
    league = League.create(
        "Empty Backfill",
        None,
        "fixture-host-token",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
    )
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()

    await session.execute(text(_BACKFILL_SQL))
    await session.commit()

    row = await session.execute(
        text("SELECT latest_match_date FROM leagues WHERE league_id = :league_id"),
        {"league_id": league.league_id.value},
    )

    assert row.scalar_one() is None
