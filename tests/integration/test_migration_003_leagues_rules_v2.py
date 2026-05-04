"""Behavior test for alembic 003 (leagues.rules v1 -> v2 backfill).

The integration test database is normally already at HEAD when tests run, so
v1-shaped rows are not present. This test inserts a v1 row directly, executes
the same SQL alembic 003 runs in `upgrade()`, and asserts the row was rewritten
to a v2 shape with the expected defaults. It also confirms the migration is
idempotent (re-running it does not double-apply) and that v2 rows are left
untouched.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_V1_RULES = {
    "version": 1,
    "match_pair_idempotency": "none",
    "one_team_per_player": True,
}

_V2_PATCH = {
    "version": 2,
    "ranking_subject": "team",
    "tie_breakers": ["matches_won"],
}

_UPGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int = 1"
)


async def _insert_league_with_raw_rules(
    session: AsyncSession,
    rules: dict,
    title: str,
) -> uuid.UUID:
    league_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO leagues (league_id, title, title_normalized, host_token, rules) "
            "VALUES (:lid, :title, :tnorm, :ht, CAST(:rules AS jsonb))"
        ),
        {
            "lid": league_id,
            "title": title,
            "tnorm": title.lower().strip(),
            "ht": "fixture-host-token",
            "rules": json.dumps(rules),
        },
    )
    await session.commit()
    return league_id


async def _read_rules(session: AsyncSession, league_id: uuid.UUID) -> dict:
    row = await session.execute(
        text("SELECT rules FROM leagues WHERE league_id = :lid"),
        {"lid": league_id},
    )
    raw = row.scalar_one()
    return raw if isinstance(raw, dict) else json.loads(raw)


class TestMigration003:
    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_v1_row_is_upgraded_to_v2_with_defaults(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session, _V1_RULES, "Migration Test League"
        )

        await session.execute(text(_UPGRADE_SQL), {"patch": json.dumps(_V2_PATCH)})
        await session.commit()

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 2
        assert rules["ranking_subject"] == "team"
        assert rules["tie_breakers"] == ["matches_won"]
        # Untouched fields preserved.
        assert rules["match_pair_idempotency"] == "none"
        assert rules["one_team_per_player"] is True

    async def test_migration_is_idempotent_for_v2_rows(
        self, session: AsyncSession
    ) -> None:
        existing_v2_rules = {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won", "games_diff"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, existing_v2_rules, "Already V2 League"
        )

        await session.execute(text(_UPGRADE_SQL), {"patch": json.dumps(_V2_PATCH)})
        await session.commit()

        rules = await _read_rules(session, league_id)
        # The upgrade SQL filters on version=1 so v2 rows must be untouched.
        assert rules == existing_v2_rules
