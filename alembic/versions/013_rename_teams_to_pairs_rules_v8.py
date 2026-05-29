"""Rename teams to pairs and bump rules to v8

Revision ID: 013
Revises: 012
Create Date: 2026-05-29

This is an intentional breaking vocabulary migration. Historical revisions
still document the old table/column/rule names; this head schema uses pair
terminology throughout.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def _rename_constraint_if_exists(table_name: str, old_name: str, new_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = '{table_name}'::regclass
                      AND conname = '{old_name}'
                ) THEN
                    ALTER TABLE {table_name} RENAME CONSTRAINT {old_name} TO {new_name};
                END IF;
            END $$;
            """
        )
    )


def _rename_index_if_exists(old_name: str, new_name: str) -> None:
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_class
                    WHERE relkind = 'i'
                      AND relname = '{old_name}'
                ) THEN
                    ALTER INDEX {old_name} RENAME TO {new_name};
                END IF;
            END $$;
            """
        )
    )


def upgrade() -> None:
    op.rename_table("teams", "pairs")
    op.alter_column(
        "pairs",
        "team_id",
        new_column_name="pair_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "team1_id",
        new_column_name="pair1_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "team2_id",
        new_column_name="pair2_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "team1_score",
        new_column_name="pair1_score",
        existing_type=sa.String(),
    )
    op.alter_column(
        "matches",
        "team2_score",
        new_column_name="pair2_score",
        existing_type=sa.String(),
    )

    _rename_constraint_if_exists("pairs", "teams_pkey", "pairs_pkey")
    _rename_constraint_if_exists("pairs", "teams_league_id_fkey", "pairs_league_id_fkey")
    _rename_constraint_if_exists(
        "pairs", "teams_player_id_1_fkey", "pairs_player_id_1_fkey"
    )
    _rename_constraint_if_exists(
        "pairs", "teams_player_id_2_fkey", "pairs_player_id_2_fkey"
    )
    _rename_constraint_if_exists(
        "pairs", "uq_teams_league_players", "uq_pairs_league_players"
    )
    _rename_constraint_if_exists(
        "matches", "matches_team1_id_fkey", "matches_pair1_id_fkey"
    )
    _rename_constraint_if_exists(
        "matches", "matches_team2_id_fkey", "matches_pair2_id_fkey"
    )

    _rename_index_if_exists("ix_teams_league_id", "ix_pairs_league_id")
    _rename_index_if_exists("ix_matches_team1_id", "ix_matches_pair1_id")
    _rename_index_if_exists("ix_matches_team2_id", "ix_matches_pair2_id")

    op.execute(
        sa.text(
            """
            UPDATE leagues
            SET rules =
                (
                    rules
                    - 'version'
                    - 'match_pair_idempotency'
                    - 'one_team_per_player'
                    - 'ranking_subject'
                )
                || jsonb_build_object(
                    'version', 8,
                    'pair_matchup_idempotency',
                    COALESCE(
                        rules->>'match_pair_idempotency',
                        rules->>'pair_matchup_idempotency',
                        'none'
                    ),
                    'one_pair_per_player',
                    COALESCE(
                        (rules->>'one_team_per_player')::boolean,
                        (rules->>'one_pair_per_player')::boolean,
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
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE leagues
            SET rules =
                (
                    rules
                    - 'version'
                    - 'pair_matchup_idempotency'
                    - 'one_pair_per_player'
                    - 'ranking_subject'
                )
                || jsonb_build_object(
                    'version', 7,
                    'match_pair_idempotency',
                    COALESCE(
                        rules->>'pair_matchup_idempotency',
                        rules->>'match_pair_idempotency',
                        'none'
                    ),
                    'one_team_per_player',
                    COALESCE(
                        (rules->>'one_pair_per_player')::boolean,
                        (rules->>'one_team_per_player')::boolean,
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
        )
    )

    _rename_index_if_exists("ix_pairs_league_id", "ix_teams_league_id")
    _rename_index_if_exists("ix_matches_pair1_id", "ix_matches_team1_id")
    _rename_index_if_exists("ix_matches_pair2_id", "ix_matches_team2_id")

    _rename_constraint_if_exists("pairs", "pairs_pkey", "teams_pkey")
    _rename_constraint_if_exists("pairs", "pairs_league_id_fkey", "teams_league_id_fkey")
    _rename_constraint_if_exists(
        "pairs", "pairs_player_id_1_fkey", "teams_player_id_1_fkey"
    )
    _rename_constraint_if_exists(
        "pairs", "pairs_player_id_2_fkey", "teams_player_id_2_fkey"
    )
    _rename_constraint_if_exists(
        "pairs", "uq_pairs_league_players", "uq_teams_league_players"
    )
    _rename_constraint_if_exists(
        "matches", "matches_pair1_id_fkey", "matches_team1_id_fkey"
    )
    _rename_constraint_if_exists(
        "matches", "matches_pair2_id_fkey", "matches_team2_id_fkey"
    )

    op.alter_column(
        "pairs",
        "pair_id",
        new_column_name="team_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "pair1_id",
        new_column_name="team1_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "pair2_id",
        new_column_name="team2_id",
        existing_type=postgresql.UUID(as_uuid=True),
    )
    op.alter_column(
        "matches",
        "pair1_score",
        new_column_name="team1_score",
        existing_type=sa.String(),
    )
    op.alter_column(
        "matches",
        "pair2_score",
        new_column_name="team2_score",
        existing_type=sa.String(),
    )
    op.rename_table("pairs", "teams")
