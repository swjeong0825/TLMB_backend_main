"""Add singles matches

Revision ID: 014
Revises: 013
Create Date: 2026-05-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column("latest_match_date_single", sa.Date(), nullable=True),
    )
    op.create_table(
        "singles_matches",
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player1_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player2_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player1_score", sa.String(), nullable=False),
        sa.Column("player2_score", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"],
            ["leagues.league_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["player1_id"], ["players.player_id"]),
        sa.ForeignKeyConstraint(["player2_id"], ["players.player_id"]),
        sa.PrimaryKeyConstraint("match_id"),
    )
    op.create_index(
        "ix_singles_matches_league_created",
        "singles_matches",
        ["league_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_singles_matches_player1_id",
        "singles_matches",
        ["player1_id"],
        unique=False,
    )
    op.create_index(
        "ix_singles_matches_player2_id",
        "singles_matches",
        ["player2_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_singles_matches_player2_id", table_name="singles_matches")
    op.drop_index("ix_singles_matches_player1_id", table_name="singles_matches")
    op.drop_index("ix_singles_matches_league_created", table_name="singles_matches")
    op.drop_table("singles_matches")
    op.drop_column("leagues", "latest_match_date_single")
