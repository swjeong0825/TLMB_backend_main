"""Rename eligible_players -> allowlist_entries and bump leagues.rules to v5

Revision ID: 006
Revises: 005
Create Date: 2026-05-12

Terminology unification (see top-level docs `allowlist_ai_agent_guide.md`,
`allowlist_chat_intents_context.md`, `allowlist_frontend_context.md`, and
backend design doc `Design_Doc/TLMB_Design_doc/20_allowlist.md`). The feature
previously called "eligible players" is now uniformly named "allowlist".

This migration covers two coupled changes:

1. Rename the `eligible_players` table to `allowlist_entries`, the
   `eligible_player_id` primary-key column to `allowlist_entry_id`, and the
   matching index / unique constraint / pkey to the `allowlist_entries_*`
   names. No data is moved; rows survive verbatim.
2. Bump every `leagues.rules` JSONB row from `version=4` to `version=5` and
   replace the legacy `require_eligible_players` key with the new
   `require_allowlist` key, preserving the boolean value.

Both halves are bundled because shipping them separately would leave an
inconsistent terminology window. The forward step is **idempotent** for
v5 rows via the `WHERE (rules->>'version')::int = 4` filter on the JSONB
update.

**Downgrade restores both the old table identifiers and the legacy JSONB
key**, so a deploy can roll back end-to-end without manual data fixups.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


_UPGRADE_RULES_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_eligible_players') "
    "       || jsonb_build_object("
    "              'version', 5, "
    "              'require_allowlist', "
    "              COALESCE((rules->>'require_eligible_players')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 4"
)

_DOWNGRADE_RULES_SQL = (
    "UPDATE leagues "
    "SET rules = (rules - 'require_allowlist') "
    "       || jsonb_build_object("
    "              'version', 4, "
    "              'require_eligible_players', "
    "              COALESCE((rules->>'require_allowlist')::bool, false)"
    "          ) "
    "WHERE (rules->>'version')::int = 5"
)


def upgrade() -> None:
    op.rename_table("eligible_players", "allowlist_entries")
    op.alter_column(
        "allowlist_entries",
        "eligible_player_id",
        new_column_name="allowlist_entry_id",
    )
    op.execute(
        "ALTER INDEX ix_eligible_players_league_id "
        "RENAME TO ix_allowlist_entries_league_id"
    )
    op.execute(
        "ALTER TABLE allowlist_entries "
        "RENAME CONSTRAINT uq_eligible_players_league_nickname "
        "TO uq_allowlist_entries_league_nickname"
    )
    op.execute(
        "ALTER TABLE allowlist_entries "
        "RENAME CONSTRAINT eligible_players_pkey "
        "TO allowlist_entries_pkey"
    )

    op.execute(sa.text(_UPGRADE_RULES_SQL))


def downgrade() -> None:
    op.execute(sa.text(_DOWNGRADE_RULES_SQL))

    op.execute(
        "ALTER TABLE allowlist_entries "
        "RENAME CONSTRAINT allowlist_entries_pkey "
        "TO eligible_players_pkey"
    )
    op.execute(
        "ALTER TABLE allowlist_entries "
        "RENAME CONSTRAINT uq_allowlist_entries_league_nickname "
        "TO uq_eligible_players_league_nickname"
    )
    op.execute(
        "ALTER INDEX ix_allowlist_entries_league_id "
        "RENAME TO ix_eligible_players_league_id"
    )
    op.alter_column(
        "allowlist_entries",
        "allowlist_entry_id",
        new_column_name="eligible_player_id",
    )
    op.rename_table("allowlist_entries", "eligible_players")
