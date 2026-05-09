"""Behavior test for alembic 004 (leagues.rules v2 -> v3 backfill + cross-rule rewrite).

The integration test database is normally already at HEAD when tests run, so
v2-shaped rows are not present. This test inserts v2 rows directly, executes
the same SQL alembic 004 runs in `upgrade()`, and asserts:

1. Every v1/v2 row is bumped to v3.
2. `(player, OTPP=true)` rows are rewritten to `(team, OTPP=true)`.
3. Custom `tie_breakers` are preserved verbatim.
4. The migration is idempotent (re-running on v3 rows is a no-op).
5. Downgrade resets `version` to `2` for v3 rows; the rewritten
   `ranking_subject` is **not** restored (irreversible by design).
"""
from __future__ import annotations

import json
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_REWRITE_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int IN (1, 2) "
    "  AND (rules->>'ranking_subject') = 'player' "
    "  AND (rules->>'one_team_per_player')::bool = true"
)
_BUMP_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int IN (1, 2)"
)
_DOWNGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int = 3"
)

_REWRITE_PATCH = {"version": 3, "ranking_subject": "team"}
_BUMP_PATCH = {"version": 3}
_DOWNGRADE_PATCH = {"version": 2}


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
    await session.execute(text(_REWRITE_SQL), {"patch": json.dumps(_REWRITE_PATCH)})
    await session.execute(text(_BUMP_SQL), {"patch": json.dumps(_BUMP_PATCH)})
    await session.commit()


async def _run_downgrade(session: AsyncSession) -> None:
    await session.execute(text(_DOWNGRADE_SQL), {"patch": json.dumps(_DOWNGRADE_PATCH)})
    await session.commit()


class TestMigration004:
    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_team_otpp_true_v2_row_is_bumped_to_v3(
        self, session: AsyncSession
    ) -> None:
        v2_team_otpp_true = {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v2_team_otpp_true, "Team OTPP True"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 3
        # Untouched fields preserved.
        assert rules["ranking_subject"] == "team"
        assert rules["one_team_per_player"] is True
        assert rules["match_pair_idempotency"] == "once_per_league"
        assert rules["tie_breakers"] == ["matches_won"]

    async def test_player_otpp_true_v2_row_is_rewritten_to_team_otpp_true(
        self, session: AsyncSession
    ) -> None:
        v2_player_otpp_true = {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v2_player_otpp_true, "Player OTPP True (legacy)"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 3
        # Cross-rule rewrite: ranking_subject flipped to "team".
        assert rules["ranking_subject"] == "team"
        assert rules["one_team_per_player"] is True
        # tie_breakers preserved verbatim.
        assert rules["tie_breakers"] == ["matches_won"]
        assert rules["match_pair_idempotency"] == "once_per_league"

    async def test_custom_tie_breakers_preserved_through_rewrite(
        self, session: AsyncSession
    ) -> None:
        custom_tie_breakers = ["games_won", "games_diff"]
        v2_team_with_custom_tbs = {
            "version": 2,
            "match_pair_idempotency": "none",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": custom_tie_breakers,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v2_team_with_custom_tbs, "Team Custom TBs"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 3
        assert rules["tie_breakers"] == custom_tie_breakers

    async def test_player_otpp_true_with_custom_tie_breakers_preserves_them(
        self, session: AsyncSession
    ) -> None:
        """The cross-rule rewrite must not clobber tie_breakers."""
        custom_tie_breakers = ["games_won", "games_diff"]
        v2_player_otpp_true_custom = {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "player",
            "tie_breakers": custom_tie_breakers,
        }
        league_id = await _insert_league_with_raw_rules(
            session, v2_player_otpp_true_custom, "Player OTPP True Custom TBs"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 3
        assert rules["ranking_subject"] == "team"
        assert rules["tie_breakers"] == custom_tie_breakers

    async def test_upgrade_is_idempotent_for_v3_rows(
        self, session: AsyncSession
    ) -> None:
        existing_v3 = {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won", "games_diff"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, existing_v3, "Already V3"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        # The upgrade SQL filters by version IN (1, 2), so v3 rows are untouched.
        assert rules == existing_v3

    async def test_downgrade_resets_version_to_2_but_does_not_restore_ranking_subject(
        self, session: AsyncSession
    ) -> None:
        v2_player_otpp_true = {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v2_player_otpp_true, "Player OTPP True (downgrade test)"
        )

        await _run_upgrade(session)
        await _run_downgrade(session)

        rules = await _read_rules(session, league_id)
        # version reset.
        assert rules["version"] == 2
        # ranking_subject NOT restored — this is the irreversible part of the
        # rewrite, documented in the migration module docstring.
        assert rules["ranking_subject"] == "team"
        assert rules["one_team_per_player"] is True
