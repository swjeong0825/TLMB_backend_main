"""leagues rules v2 (ranking_subject + tie_breakers)

Revision ID: 003
Revises: 002
Create Date: 2026-05-04

Backfills the JSONB `leagues.rules` column from v1 to v2 by injecting the v2
ranking defaults (`ranking_subject="team"`, `tie_breakers=["matches_won"]`) and
bumping `version` to 2. v2 defaults reproduce v1 behavior byte-for-byte, so
existing leagues see no change in standings output.

No DDL — the column stays JSONB; only its in-flight content shape changes.

See backend_main/Design_Doc/TLMB_Design_doc/17_configurable_ranking.md.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


_V2_DEFAULTS = {
    "version": 2,
    "ranking_subject": "team",
    "tie_breakers": ["matches_won"],
}


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int = 1"
        ),
        {"patch": json.dumps(_V2_DEFAULTS)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = (rules - 'ranking_subject' - 'tie_breakers') "
            "       || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int = 2"
        ),
        {"patch": json.dumps({"version": 1})},
    )
