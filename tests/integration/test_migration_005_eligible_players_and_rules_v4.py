"""Behavior test for alembic 005 (eligible_players table + leagues.rules v3 -> v4 backfill).

The integration test database is at HEAD when tests run, so v3-shaped rows
are not present. This test inserts v3 rows directly, executes the same SQL
that alembic 005 runs in `upgrade()`, and asserts:

1. Every v3 row is bumped to v4 with `require_eligible_players: false`.
2. v4 rows are untouched (idempotent re-run).
3. Other rule fields (`one_team_per_player`, `ranking_subject`, `tie_breakers`,
   `match_pair_idempotency`) are preserved verbatim through the bump.
4. Downgrade resets `version` to `3`; the `require_eligible_players` key is
   left in place (extra keys are ignored by the v3 parser).
5. The `eligible_players` table is created by the migration's `op.create_table`
   call — exercised structurally via insert + uniqueness assertions.
"""
from __future__ import annotations

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_BUMP_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int = 3"
)
_DOWNGRADE_SQL = (
    "UPDATE leagues "
    "SET rules = rules || CAST(:patch AS jsonb) "
    "WHERE (rules->>'version')::int = 4"
)
_BUMP_PATCH = {"version": 4, "require_eligible_players": False}
_DOWNGRADE_PATCH = {"version": 3}


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
    await session.execute(text(_BUMP_SQL), {"patch": json.dumps(_BUMP_PATCH)})
    await session.commit()


async def _run_downgrade(session: AsyncSession) -> None:
    await session.execute(text(_DOWNGRADE_SQL), {"patch": json.dumps(_DOWNGRADE_PATCH)})
    await session.commit()


class TestMigration005Rules:
    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_v3_row_is_bumped_to_v4_with_flag_false(
        self, session: AsyncSession
    ) -> None:
        v3_row = {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v3_row, "V3 Default League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 4
        assert rules["require_eligible_players"] is False
        # Other fields preserved verbatim.
        assert rules["match_pair_idempotency"] == "once_per_league"
        assert rules["one_team_per_player"] is True
        assert rules["ranking_subject"] == "team"
        assert rules["tie_breakers"] == ["matches_won"]

    async def test_custom_v3_rules_preserved_through_bump(
        self, session: AsyncSession
    ) -> None:
        custom_v3 = {
            "version": 3,
            "match_pair_idempotency": "none",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["games_won", "games_diff"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, custom_v3, "V3 Custom League"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        assert rules["version"] == 4
        assert rules["require_eligible_players"] is False
        assert rules["match_pair_idempotency"] == "none"
        assert rules["one_team_per_player"] is False
        assert rules["ranking_subject"] == "player"
        assert rules["tie_breakers"] == ["games_won", "games_diff"]

    async def test_upgrade_is_idempotent_for_v4_rows(
        self, session: AsyncSession
    ) -> None:
        existing_v4 = {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
        league_id = await _insert_league_with_raw_rules(
            session, existing_v4, "Already V4"
        )

        await _run_upgrade(session)

        rules = await _read_rules(session, league_id)
        # Filter on version=3 keeps v4 rows untouched, including a True flag.
        assert rules == existing_v4

    async def test_downgrade_resets_version_to_3_but_does_not_drop_flag(
        self, session: AsyncSession
    ) -> None:
        v3_row = {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
        league_id = await _insert_league_with_raw_rules(
            session, v3_row, "Downgrade Test League"
        )

        await _run_upgrade(session)
        await _run_downgrade(session)

        rules = await _read_rules(session, league_id)
        # Version reset.
        assert rules["version"] == 3
        # The flag is intentionally NOT dropped on downgrade — extra keys are
        # ignored by the v3 parser, so leaving it in place is harmless and
        # keeps the migration cheap.
        assert rules["require_eligible_players"] is False


class TestMigration005EligiblePlayersTable:
    """Smoke checks that the new table exists with the right shape."""

    @pytest_asyncio.fixture
    async def session(
        self, session_factory: async_sessionmaker[AsyncSession]
    ):
        async with session_factory() as s:
            yield s

    async def test_table_accepts_insert(self, session: AsyncSession) -> None:
        # Need a real league to satisfy the FK.
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 4,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_eligible_players": False,
            },
            "FK Test League",
        )

        ep_id = uuid.uuid4()
        await session.execute(
            text(
                "INSERT INTO eligible_players (eligible_player_id, league_id, nickname_normalized) "
                "VALUES (:epid, :lid, :nick)"
            ),
            {"epid": ep_id, "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        row = await session.execute(
            text(
                "SELECT nickname_normalized FROM eligible_players "
                "WHERE eligible_player_id = :epid"
            ),
            {"epid": ep_id},
        )
        assert row.scalar_one() == "alex"

    async def test_uniqueness_constraint_on_league_plus_nickname(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 4,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_eligible_players": False,
            },
            "Uniq Test League",
        )

        await session.execute(
            text(
                "INSERT INTO eligible_players (eligible_player_id, league_id, nickname_normalized) "
                "VALUES (:epid, :lid, :nick)"
            ),
            {"epid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        with pytest.raises(IntegrityError):
            await session.execute(
                text(
                    "INSERT INTO eligible_players (eligible_player_id, league_id, nickname_normalized) "
                    "VALUES (:epid, :lid, :nick)"
                ),
                {"epid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
            )
            await session.commit()
        await session.rollback()

    async def test_cascade_delete_on_league_removes_eligible_rows(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 4,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_eligible_players": False,
            },
            "Cascade Test League",
        )

        await session.execute(
            text(
                "INSERT INTO eligible_players (eligible_player_id, league_id, nickname_normalized) "
                "VALUES (:epid, :lid, :nick)"
            ),
            {"epid": uuid.uuid4(), "lid": league_id, "nick": "alex"},
        )
        await session.commit()

        await session.execute(
            text("DELETE FROM leagues WHERE league_id = :lid"), {"lid": league_id}
        )
        await session.commit()

        row = await session.execute(
            text(
                "SELECT COUNT(*) FROM eligible_players WHERE league_id = :lid"
            ),
            {"lid": league_id},
        )
        assert row.scalar_one() == 0
