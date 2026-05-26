"""Add latest match date metadata to leagues

Revision ID: 010
Revises: 009
Create Date: 2026-05-25

`latest_match_date` is denormalized league metadata used by the frontend to
default date-filtered standings without fetching match history first. It is a
league-local date derived from match `created_at` and `league_timezone`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("leagues", sa.Column("latest_match_date", sa.Date(), nullable=True))
    op.execute(
        sa.text(
            "UPDATE leagues AS l "
            "SET latest_match_date = latest.latest_match_date "
            "FROM ("
            "    SELECT "
            "        m.league_id, "
            "        MAX((m.created_at AT TIME ZONE l2.league_timezone)::date) "
            "            AS latest_match_date "
            "    FROM matches AS m "
            "    JOIN leagues AS l2 ON l2.league_id = m.league_id "
            "    GROUP BY m.league_id"
            ") AS latest "
            "WHERE l.league_id = latest.league_id"
        )
    )


def downgrade() -> None:
    op.drop_column("leagues", "latest_match_date")
