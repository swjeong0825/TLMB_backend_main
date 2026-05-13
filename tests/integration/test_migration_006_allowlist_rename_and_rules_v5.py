"""Behavior test for alembic 006 (allowlist rename + leagues.rules v4 -> v5).

The integration test database is at HEAD when tests run, so v4-shaped rows
are not present and the table is already named `allowlist_entries`. This
test inserts v4-shaped JSONB rows directly and executes the same JSONB
update statements that alembic 006 runs in `upgrade()` / `downgrade()`,
asserting that:

1. Every v4 row is bumped to v5: the `require_eligible_players` key is
   dropped and `require_allowlist` is set to the same boolean value.
2. v5 rows are untouched (idempotent re-run).
3. Other rule fields (`one_team_per_player`, `ranking_subject`,
   `tie_breakers`, `match_pair_idempotency`) are preserved verbatim.
4. Downgrade restores the legacy `require_eligible_players` key with the
   same boolean value, drops `require_allowlist`, and resets `version` to 4.
5. The `allowlist_entries` table (the renamed shape) accepts inserts under
   the new `allowlist_entry_id` column, enforces the renamed unique
   constraint, and cascades deletes when the parent league row is removed.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_UPGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_eligible_players') "
    "       || jsonb_build_object("
    "              'version', 5, "
    "              'require_allowlist', "
    "              COALESCE((rules->>'require_eligible_players')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 4"
)

_DOWNGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_allowlist') "
    "       || jsonb_build_object("
    "              'version', 4, "
    "              'require_eligible_players', "
    "              COALESCE((rules->>'require_allowlist')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 5"
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


async def _run_upgrade(session: AsyncSession) -> None:
    await session.execute(text(_UPGRADE_SQL))
    await session.commit()


async def _run_downgrade(session: AsyncSession) -> None:
    await session.execute(text(_DOWNGRADE_SQL))
    await session.commit()


class TestMigration006Rules:
    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_v4_row_with_flag_false_is_renamed_and_bumped(
        self, session: AsyncSession
    ) -> None:
        v4_row = {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": False,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v4_row, "V4 False Flag League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 5
        assert rules["require_allowlist"] is False
        assert "require_eligible_players" not in rules
        assert rules["match_pair_idempotency"] == "once_per_league"
        assert rules["one_team_per_player"] is True
        assert rules["ranking_subject"] == "team"
        assert rules["tie_breakers"] == ["matches_won"]

    async def test_v4_row_with_flag_true_preserves_value(
        self, session: AsyncSession
    ) -> None:
        v4_row = {
            "version": 4,
            "match_pair_idempotency": "none",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["games_won", "games_diff"],
            "require_eligible_players": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v4_row, "V4 True Flag Custom League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 5
        assert rules["require_allowlist"] is True
        assert "require_eligible_players" not in rules
        assert rules["match_pair_idempotency"] == "none"
        assert rules["one_team_per_player"] is False
        assert rules["ranking_subject"] == "player"
        assert rules["tie_breakers"] == ["games_won", "games_diff"]

    async def test_upgrade_is_idempotent_for_v5_rows(
        self, session: AsyncSession
    ) -> None:
        existing_v5 = {
            "version": 5,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, existing_v5, "Already V5"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules == existing_v5

    async def test_downgrade_restores_legacy_key_and_v4(
        self, session: AsyncSession
    ) -> None:
        v4_row = {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v4_row, "Roundtrip Test League"
        )

        await _run_upgrade(session)
        await _run_downgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 4
        assert rules["require_eligible_players"] is True
        assert "require_allowlist" not in rules


class TestMigration006AllowlistTable:
    """Smoke checks that the renamed table has the expected shape at HEAD."""

    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_table_accepts_insert(self, session: AsyncSession) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 5,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_allowlist": False,
            },
            "FK Allowlist Test League",
        )

        entry_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO allowlist_entries "
                "(allowlist_entry_id, league_id, nickname_normalized) "
                "VALUES (:eid, :lid, :nick)"
            ),
            {"eid": entry_id, "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        row = await session.execute(
            text(
                "SELECT nickname_normalized FROM allowlist_entries "
                "WHERE allowlist_entry_id = :eid"
            ),
            {"eid": entry_id},
        )
        assert row.scalar_one() == "alex"

    async def test_uniqueness_constraint_on_league_plus_nickname(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 5,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_allowlist": False,
            },
            "Uniq Allowlist Test League",
        )

        await session.execute(
            text(
                "INSERT INTO allowlist_entries "
                "(allowlist_entry_id, league_id, nickname_normalized) "
                "VALUES (:eid, :lid, :nick)"
            ),
            {"eid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO allowlist_entries "
                    "(allowlist_entry_id, league_id, nickname_normalized) "
                    "VALUES (:eid, :lid, :nick)"
                ),
                {"eid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
            )
            await session.commit()
        await session.rollback()

    async def test_cascade_delete_on_league_removes_allowlist_rows(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 5,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_allowlist": False,
            },
            "Cascade Allowlist Test League",
        )

        await session.execute(
            text(
                "INSERT INTO allowlist_entries "
                "(allowlist_entry_id, league_id, nickname_normalized) "
                "VALUES (:eid, :lid, :nick)"
            ),
            {"eid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        await session.execute(
            text("DELETE FROM leagues WHERE league_id = :lid"), {"lid": league_id}
        )
        await session.commit()

        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM allowlist_entries WHERE league_id = :lid"
            ),
            {"lid": league_id},
        )
        assert row.scalar_one() == 0
