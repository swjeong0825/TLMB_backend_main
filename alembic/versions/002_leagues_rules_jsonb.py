"""leagues rules jsonb

Revision ID: 002
Revises: 001
Create Date: 2026-04-08

"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

_DEFAULT_RULES_V1 = {
    "version": 1,
    "match_pair_idempotency": "none",
    "one_team_per_player": True,
}


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE leagues SET rules = CAST(:rules AS jsonb) WHERE rules IS NULL"),
        {"rules": json.dumps(_DEFAULT_RULES_V1)},
    )
    op.alter_column(
        "leagues",
        "rules",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column("leagues", "rules")
