"""leagues rules v3 (one_team_per_player unlocked + cross-rule)

Revision ID: 004
Revises: 003
Create Date: 2026-05-08

Bumps every existing league row's rules version from v1/v2 to v3, and rewrites
every `(ranking_subject="player", one_team_per_player=true)` row to
`(ranking_subject="team", one_team_per_player=true)` so the v3 cross-rule is
satisfied. `tie_breakers` is preserved verbatim — host metric choices are not
lost.

Rationale (full design doc:
backend_main/Design_Doc/TLMB_Design_doc/18_configurable_ranking_v3.md):
- v2 leagues all have `one_team_per_player = true` (locked at validation
  time), so the only existing combo that becomes illegal under v3 is
  `(player, OTPP=true)`. That combo's standings are mathematically equivalent
  to `(team, OTPP=true)` (every teammate has identical metric tuples), so the
  user-visible information is preserved by the rewrite — only the rendering
  shape changes (rows collapse from one-per-player back to one-per-team,
  halving row count for affected leagues).

**Downgrade is best-effort and irreversible for the rewrite:** the original
`(player, OTPP=true)` value cannot be recovered after upgrade because
`ranking_subject` is overwritten in place. Operators who need a recovery path
must take a manual JSONB snapshot of the `leagues.rules` column before running
the upgrade. The downgrade only resets `version` to `2` for v3 rows.

No DDL — the column stays JSONB; only its in-flight content shape changes.
The migration is idempotent (re-running on v3 rows is a no-op because both
`UPDATE` statements filter by `version IN (1, 2)`).
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


_REWRITE_PLAYER_OTPP_TRUE = {"version": 3, "ranking_subject": "team"}
_BUMP_TO_V3 = {"version": 3}
_DOWNGRADE_TO_V2 = {"version": 2}


def upgrade() -> None:
    bind = op.get_bind()
    # Step 1: rewrite (player, OTPP=true) rows to (team, OTPP=true) and bump to v3.
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int IN (1, 2) "
            "  AND (rules->>'ranking_subject') = 'player' "
            "  AND (rules->>'one_team_per_player')::bool = true"
        ),
        {"patch": json.dumps(_REWRITE_PLAYER_OTPP_TRUE)},
    )
    # Step 2: bump everyone else (v1 or v2) to v3 in place.
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int IN (1, 2)"
        ),
        {"patch": json.dumps(_BUMP_TO_V3)},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE leagues "
            "SET rules = rules || CAST(:patch AS jsonb) "
            "WHERE (rules->>'version')::int = 3"
        ),
        {"patch": json.dumps(_DOWNGRADE_TO_V2)},
    )
