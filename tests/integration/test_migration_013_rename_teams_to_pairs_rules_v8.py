"""Behavior test for alembic 013 (teams -> pairs, rules v8).

The integration database is normally at HEAD. These tests verify that the head
schema exposes the pair-named tables/columns and that the JSONB rules rewrite
converts v7 rows to the v8 pair contract.
"""
from __future__ import annotations

import json
import uuid

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


_UPGRADE_RULES_SQL = """
UPDATE leagues
SET rules = (
    rules
    - 'match_pair_idempotency'
    - 'one_team_per_player'
)
|| jsonb_build_object(
    'version', 8,
    'pair_matchup_idempotency',
        COALESCE(
            rules->>'pair_matchup_idempotency',
            rules->>'match_pair_idempotency',
            'none'
        ),
    'one_pair_per_player',
        COALESCE(
            (rules->>'one_pair_per_player')::boolean,
            (rules->>'one_team_per_player')::boolean,
            true
        ),
    'ranking_subject',
        CASE
            WHEN rules->>'ranking_subject' = 'team' THEN 'pair'
            ELSE COALESCE(rules->>'ranking_subject', 'pair')
        END
)
WHERE COALESCE((rules->>'version')::int, 1) <= 7
"""


_DOWNGRADE_RULES_SQL = """
UPDATE leagues
SET rules = (
    rules
    - 'pair_matchup_idempotency'
    - 'one_pair_per_player'
)
|| jsonb_build_object(
    'version', 7,
    'match_pair_idempotency',
        COALESCE(
            rules->>'match_pair_idempotency',
            rules->>'pair_matchup_idempotency',
            'none'
        ),
    'one_team_per_player',
        COALESCE(
            (rules->>'one_team_per_player')::boolean,
            (rules->>'one_pair_per_player')::boolean,
            true
        ),
    'ranking_subject',
        CASE
            WHEN rules->>'ranking_subject' = 'pair' THEN 'team'
            ELSE COALESCE(rules->>'ranking_subject', 'team')
        END
)
WHERE COALESCE((rules->>'version')::int, 8) = 8
"""


async def _read_rules(session: AsyncSession, league_id: uuid.UUID) -> dict:
    row = await session.execute(
        text("SELECT rules FROM leagues WHERE league_id = :lid"),
        {"lid": league_id},
    )
    raw = row.scalar_one()
    return raw if isinstance(raw, dict) else json.loads(raw)


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


class TestMigration013:
    @pytest_asyncio.fixture
    async def session(self, session_factory: async_sessionmaker[AsyncSession]):
        async with session_factory() as s:
            yield s

    async def test_head_schema_uses_pair_table_and_match_columns(
        self, session: AsyncSession
    ) -> None:
        tables_result = await session.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('teams', 'pairs')"
            )
        )
        tables = {row.table_name for row in tables_result}
        assert "pairs" in tables
        assert "teams" not in tables

        columns_result = await session.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name IN ('pairs', 'matches')"
            )
        )
        columns = {(row.table_name, row.column_name) for row in columns_result}

        assert ("pairs", "pair_id") in columns
        assert ("matches", "pair1_id") in columns
        assert ("matches", "pair2_id") in columns
        assert ("matches", "pair1_score") in columns
        assert ("matches", "pair2_score") in columns

        assert ("pairs", "team_id") not in columns
        assert ("matches", "team1_id") not in columns
        assert ("matches", "team2_id") not in columns
        assert ("matches", "team1_score") not in columns
        assert ("matches", "team2_score") not in columns

    async def test_head_schema_uses_pair_indexes_and_constraints(
        self, session: AsyncSession
    ) -> None:
        indexes_result = await session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND indexname LIKE 'ix_%'"
            )
        )
        indexes = {row.indexname for row in indexes_result}
        assert {"ix_pairs_league_id", "ix_matches_pair1_id", "ix_matches_pair2_id"} <= indexes
        assert "ix_teams_league_id" not in indexes
        assert "ix_matches_team1_id" not in indexes
        assert "ix_matches_team2_id" not in indexes

        constraints_result = await session.execute(
            text(
                "SELECT conname FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace "
                "AND conname IN ("
                "  'uq_pairs_league_players',"
                "  'uq_teams_league_players',"
                "  'matches_pair1_id_fkey',"
                "  'matches_pair2_id_fkey',"
                "  'matches_team1_id_fkey',"
                "  'matches_team2_id_fkey'"
                ")"
            )
        )
        constraints = {row.conname for row in constraints_result}
        assert {
            "uq_pairs_league_players",
            "matches_pair1_id_fkey",
            "matches_pair2_id_fkey",
        } <= constraints
        assert "uq_teams_league_players" not in constraints
        assert "matches_team1_id_fkey" not in constraints
        assert "matches_team2_id_fkey" not in constraints

    async def test_upgrade_rewrites_v7_rules_to_v8_pair_keys(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 7,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": True,
            },
            "Rules V8 Migration",
        )

        await session.execute(text(_UPGRADE_RULES_SQL))
        rules = await _read_rules(session, league_id)
        assert rules["version"] == 8
        assert rules["pair_matchup_idempotency"] == "once_per_league"
        assert rules["one_pair_per_player"] is False
        assert rules["ranking_subject"] == "pair"
        assert "match_pair_idempotency" not in rules
        assert "one_team_per_player" not in rules

    async def test_downgrade_reverses_rules_to_v7_keys(
        self, session: AsyncSession
    ) -> None:
        league_id = await _insert_league_with_raw_rules(
            session,
            {
                "version": 8,
                "pair_matchup_idempotency": "once_per_day",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": True,
            },
            "Rules V7 Downgrade",
        )

        await session.execute(text(_DOWNGRADE_RULES_SQL))
        rules = await _read_rules(session, league_id)
        assert rules["version"] == 7
        assert rules["match_pair_idempotency"] == "once_per_day"
        assert rules["one_team_per_player"] is True
        assert rules["ranking_subject"] == "team"
        assert "pair_matchup_idempotency" not in rules
        assert "one_pair_per_player" not in rules
