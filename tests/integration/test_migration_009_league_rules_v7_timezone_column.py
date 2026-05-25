"""Behavior test for alembic 009 (rules v7 + league_timezone column).

The integration database is already at HEAD when tests run, so this test
inserts v6-shaped JSONB rows directly and executes the same JSONB update
statement that alembic 009 runs. The invariant is small but load-bearing:
existing leagues keep their stored `match_pair_idempotency`, rules do not
store timezone, and the new column has the Pacific Time default.
"""
from __future__ import annotations

import json
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_UPGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = rules || jsonb_build_object('version', 7) "
    "WHERE COALESCE((rules->>'version')::int, 1) <= 6"
)

_DOWNGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = "
    "    (rules - 'version' - 'match_pair_idempotency') "
    "    || jsonb_build_object("
    "        'version', 6, "
    "        'match_pair_idempotency', "
    "        CASE "
    "            WHEN rules->>'match_pair_idempotency' = 'once_per_day' "
    "            THEN 'once_per_league' "
    "            ELSE rules->>'match_pair_idempotency' "
    "        END"
    "    ) "
    "WHERE COALESCE((rules->>'version')::int, 7) = 7"
)


async def _insert_league_with_raw_rules(
    session: AsyncSession,
    rules: dict,
    title: str,
) -> uuid.UUID:
    league_id = uuid.uuid4()
    await session.execute(
        text(
            "INSERT INTO leagues "
            "(league_id, title, title_normalized, host_token, host_email, rules) "
            "VALUES (:lid, :title, :tnorm, :ht, :he, CAST(:rules AS jsonb))"
        ),
        {
            "lid": league_id,
            "title": title,
            "tnorm": title.lower().strip(),
            "ht": "fixture-host-token",
            "he": "fixture@example.com",
            "rules": json.dumps(rules),
        },
    )
    await session.commit()
    return league_id


async def _read_row(session: AsyncSession, league_id: uuid.UUID) -> tuple[dict, str]:
    row = await session.execute(
        text("SELECT rules, league_timezone FROM leagues WHERE league_id = :lid"),
        {"lid": league_id},
    )
    rules, league_timezone = row.one()
    parsed = rules if isinstance(rules, dict) else json.loads(rules)
    return parsed, league_timezone


async def _run_upgrade(session: AsyncSession) -> None:
    await session.execute(text(_UPGRADE_SQL))
    await session.commit()


async def _run_downgrade(session: AsyncSession) -> None:
    await session.execute(text(_DOWNGRADE_SQL))
    await session.commit()


class TestMigration009:
    @pytest_asyncio.fixture
    async def session(self, session_factory: async_sessionmaker[AsyncSession]):
        async with session_factory() as s:
            yield s

    async def test_upgrade_preserves_strictness_and_defaults_timezone_column(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 6,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": True,
            },
            "Strict Pair League",
        )

        await _run_upgrade(session)

        rules, league_timezone = await _read_row(session, league_id)
        assert rules["version"] == 7
        assert rules["match_pair_idempotency"] == "once_per_league"
        assert "league_timezone" not in rules
        assert league_timezone == "America/Los_Angeles"

    async def test_upgrade_preserves_none_pair_rule(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 6,
                "match_pair_idempotency": "none",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": True,
            },
            "Unlimited Pair League",
        )

        await _run_upgrade(session)

        rules, _ = await _read_row(session, league_id)
        assert rules["version"] == 7
        assert rules["match_pair_idempotency"] == "none"

    async def test_downgrade_maps_daily_rule_to_global_strict_v6(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 7,
                "match_pair_idempotency": "once_per_day",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": True,
            },
            "Downgrade Daily League",
        )

        await _run_downgrade(session)

        rules, _ = await _read_row(session, league_id)
        assert rules["version"] == 6
        assert rules["match_pair_idempotency"] == "once_per_league"
        assert "league_timezone" not in rules
