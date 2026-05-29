"""Behavior test for alembic 007 (drop allowlist_entries + leagues.rules v5 -> v6).

The integration test database is at HEAD when tests run, so v5-shaped rows
are not present and the `allowlist_entries` table no longer exists. This
test inserts v5-shaped JSONB rows directly and executes the same JSONB
update statements that alembic 007 runs in `upgrade()` / `downgrade()`,
asserting that:

1. Every v5 row is bumped to v6: the `require_allowlist` key is dropped and
   `auto_register_players_on_match` is set to the **inverted** boolean
   (`require_allowlist=true` becomes `auto_register_players_on_match=false`
   and vice versa).
2. v6 rows are untouched by re-running the upgrade SQL (idempotent).
3. Other rule fields (`one_pair_per_player`, `ranking_subject`,
   `tie_breakers`, `pair_matchup_idempotency`) are preserved verbatim.
4. Downgrade restores the legacy `require_allowlist` key with the
   inverted boolean value, drops `auto_register_players_on_match`, and
   resets `version` to 5.

This test does NOT exercise the table-drop step. Reasoning: by the time
the integration db is at HEAD, the table is already absent, so there is
nothing to drop. The forward-only invariant is that the existing data
(in `players`) already carries the roster.
"""
from __future__ import annotations

import json
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_UPGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_allowlist') "
    "       || jsonb_build_object("
    "              'version', 6, "
    "              'auto_register_players_on_match', "
    "              NOT COALESCE((rules->>'require_allowlist')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 5"
)

_DOWNGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'auto_register_players_on_match') "
    "       || jsonb_build_object("
    "              'version', 5, "
    "              'require_allowlist', "
    "              NOT COALESCE((rules->>'auto_register_players_on_match')::bool, true)"
    "          ) "
    "WHERE (rules->>'version')::int = 6"
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
    return league_id


async def _read_rules(session: AsyncSession, league_id: uuid.UUID) -> dict:
    row = await session.execute(
        text("SELECT rules FROM leagues WHERE league_id = :lid"),
        {"lid": league_id},
    )
    raw = row.scalar_one()
    return raw if isinstance(raw, dict) else json.loads(raw)


async def _run_upgrade(session: AsyncSession) -> None:
    await session.execute(text(_UPGRADE_SQL))


async def _run_downgrade(session: AsyncSession) -> None:
    await session.execute(text(_DOWNGRADE_SQL))


class TestMigration007:
    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_v5_require_allowlist_false_becomes_v6_auto_register_true(
        self, session: AsyncSession
    ) -> None:
        v5_row = {
            "version": 5,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "require_allowlist": False,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v5_row, "Open League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 6
        assert "require_allowlist" not in rules
        assert rules["auto_register_players_on_match"] is True
        assert rules["one_pair_per_player"] is True
        assert rules["ranking_subject"] == "pair"
        assert rules["tie_breakers"] == ["matches_won"]
        assert rules["pair_matchup_idempotency"] == "once_per_league"

    async def test_v5_require_allowlist_true_becomes_v6_auto_register_false(
        self, session: AsyncSession
    ) -> None:
        v5_row = {
            "version": 5,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v5_row, "Locked Roster League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 6
        assert "require_allowlist" not in rules
        assert rules["auto_register_players_on_match"] is False

    async def test_upgrade_is_idempotent_for_v6_rows(
        self, session: AsyncSession
    ) -> None:
        existing_v6 = {
            "version": 6,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, existing_v6, "Already V6"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules == existing_v6

    async def test_downgrade_restores_require_allowlist_with_inverted_value(
        self, session: AsyncSession
    ) -> None:
        v5_row = {
            "version": 5,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v5_row, "Round-Trip League"
        )

        await _run_upgrade(session)
        await _run_downgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 5
        assert "auto_register_players_on_match" not in rules
        assert rules["require_allowlist"] is True
        assert rules["one_pair_per_player"] is True
        assert rules["ranking_subject"] == "pair"

    async def test_downgrade_inverts_auto_register_true_to_require_allowlist_false(
        self, session: AsyncSession
    ) -> None:
        v6_row = {
            "version": 6,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v6_row, "V6 Auto-Register On"
        )

        await _run_downgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 5
        assert "auto_register_players_on_match" not in rules
        assert rules["require_allowlist"] is False

    async def test_upgrade_handles_missing_require_allowlist_key_defaults_true(
        self, session: AsyncSession
    ) -> None:
        """If a malformed v5 row is missing the `require_allowlist` key,
        the upgrade falls back to `false` (the v5 default), which inverts
        to `auto_register_players_on_match=true`."""
        v5_no_flag = {
            "version": 5,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v5_no_flag, "Missing-Flag League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 6
        assert rules["auto_register_players_on_match"] is True
