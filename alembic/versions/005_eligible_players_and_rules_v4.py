"""eligible_players table + leagues.rules v4 with require_eligible_players

Revision ID: 005
Revises: 004
Create Date: 2026-05-11

Bundles two changes that form one logical feature unit (see
backend_main/Design_Doc/TLMB_Design_doc/20_eligible_players.md):

1. Creates the new ``eligible_players`` table — host-curated allowlist of
   nicknames per league, decoupled from the roster ``players`` table.
2. Bumps every ``leagues.rules`` JSONB row from ``version=3`` to ``version=4``
   and adds ``require_eligible_players: false`` (the default for every
   pre-existing league, preserving today's behavior byte-for-byte).

The two are bundled because shipping them separately would create an awkward
intermediate state: a v4 flag pointing at a non-existent table, or a table
with no way to opt into enforcement. The forward step is **idempotent** for
v4 rows via the ``WHERE (rules->>'version')::int = 3`` filter.

**Downgrade is destructive for the new table:** dropping
``eligible_players`` permanently deletes every host-curated nickname. The
JSONB rules step on downgrade only resets ``version`` to ``3``; the
``require_eligible_players`` key is left in place (extra keys are ignored by
the v3 parser, so this is harmless on read).
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


_BUMP_TO_V4 = {"version": 4, "require_eligible_players": False}
_DOWNGRADE_TO_V3 = {"version": 3}


def upgrade() -> None:
    op.create_table(
        "eligible_players",
        sa.Column(
            "eligible_player_id", postgresql.UUID(as_uuid=True), nullable=False
        ),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nickname_normalized", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["league_id"], ["leagues.league_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("eligible_player_id"),
        sa.UniqueConstraint(
            "league_id",
            "nickname_normalized",
            name="uq_eligible_players_league_nickname",
        ),
    )
    op.create_index(
        "ix_eligible_players_league_id", "eligible_players", ["league_id"]
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int = 3"
        ),
        {"patch": json.dumps(_BUMP_TO_V4)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int = 4"
        ),
        {"patch": json.dumps(_DOWNGRADE_TO_V3)},
    )

    op.drop_index("ix_eligible_players_league_id", table_name="eligible_players")
    op.drop_table("eligible_players")
