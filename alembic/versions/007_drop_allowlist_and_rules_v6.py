"""Drop allowlist_entries and bump leagues.rules to v6

Revision ID: 007
Revises: 006
Create Date: 2026-05-22

The `AllowlistEntry` entity is retired entirely. Pre-registration is now a
first-class concept implemented directly on `Player`: the host adds
players to the roster via `POST /admin/leagues/{id}/players` (no more
allowlist side table). See `Design_Doc/TLMB_Design_doc/20_roster_pre_registration.md`.

This migration covers two coupled changes:

1. Drop the `allowlist_entries` table and its `ix_allowlist_entries_league_id`
   index. No data is moved; the existing data invariant ("every
   `allowlist_entries` row has a companion `players` row" -- established
   in alembic 005's `eligible_players` rollout) means the roster already
   carries everything the v5 allowlist did. Pre-iteration leagues that
   never went through 005 may have orphan allowlist rows that are silently
   dropped here; per the forward-only invariant called out in the v5
   design doc this is acceptable.
2. Bump every `leagues.rules` JSONB row from `version=5` to `version=6`,
   replacing the `require_allowlist` key with `auto_register_players_on_match`
   and **inverting** the boolean (the new flag is the opposite framing).
   Concretely: `require_allowlist=true` becomes
   `auto_register_players_on_match=false`, and vice versa.

Both halves are bundled because shipping them separately would leave an
inconsistent state where domain code expected the new flag but the table
was still present (or vice versa).

The forward step is **idempotent** for v6 rows via the
`WHERE (rules->>'version')::int = 5` filter on the JSONB update.

**Downgrade caveats:**

- The `allowlist_entries` table is recreated empty. Pre-registered
  players added under v6 that were never on a v5 allowlist will not be
  re-materialized as allowlist rows on downgrade. They remain in the
  roster (`players` table) which is the intended forward-only behavior.
- The JSONB v6 -> v5 step inverts the boolean back symmetrically, so a
  v5 deploy reads consistent flags after the rollback.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


_UPGRADE_RULES_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_allowlist') "
    "       || jsonb_build_object("
    "              'version', 6, "
    "              'auto_register_players_on_match', "
    "              NOT COALESCE((rules->>'require_allowlist')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 5"
)

_DOWNGRADE_RULES_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'auto_register_players_on_match') "
    "       || jsonb_build_object("
    "              'version', 5, "
    "              'require_allowlist', "
    "              NOT COALESCE((rules->>'auto_register_players_on_match')::bool, true)"
    "          ) "
    "WHERE (rules->>'version')::int = 6"
)


def upgrade() -> None:
    op.drop_index("ix_allowlist_entries_league_id", table_name="allowlist_entries")
    op.drop_table("allowlist_entries")

    op.execute(sa.text(_UPGRADE_RULES_SQL))


def downgrade() -> None:
    op.execute(sa.text(_DOWNGRADE_RULES_SQL))

    op.create_table(
        "allowlist_entries",
        sa.Column(
            "allowlist_entry_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "league_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leagues.league_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nickname_normalized", sa.String(), nullable=False),
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
        sa.UniqueConstraint(
            "league_id",
            "nickname_normalized",
            name="uq_allowlist_entries_league_nickname",
        ),
    )
    op.create_index(
        "ix_allowlist_entries_league_id",
        "allowlist_entries",
        ["league_id"],
    )
