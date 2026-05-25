"""Add once_per_day rule and league timezone column

Revision ID: 009
Revises: 008
Create Date: 2026-05-25

`league_timezone` is league metadata, not a rule toggle. Existing leagues
receive the Pacific Time default used by the product, and v6 rules are upgraded
to v7 while preserving their stored `match_pair_idempotency`.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None

DEFAULT_LEAGUE_TIMEZONE = "America/Los_Angeles"


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column(
            "league_timezone",
            sa.String(),
            nullable=False,
            server_default=DEFAULT_LEAGUE_TIMEZONE,
        ),
    )
    op.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || jsonb_build_object('version', 7) "
            "WHERE COALESCE((rules->>'version')::int, 1) <= 6"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
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
    )
    op.drop_column("leagues", "league_timezone")
