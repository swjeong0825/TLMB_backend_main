"""Add host_email to leagues

Revision ID: 008
Revises: 007
Create Date: 2026-05-24

Introduces a mandatory `host_email` column on `leagues` for league host
contact. The column will be used by future notification features (e.g.
emailing the player/admin URLs at create time, new-match notifications),
but this migration only handles persistence -- sending is out of scope.

Strategy (mirrors the v2/v3/v6 "add nullable -> backfill -> set NOT NULL"
pattern used by prior migrations):

1. Add `host_email` as a nullable column so existing rows aren't blocked.
2. Backfill every existing row with the project-wide dummy address
   `glhf0825@gmail.com`. This is intentional and explicit per the
   feature request -- the application has no record of historical host
   contact info, and the dummy address documents that the value was
   inserted by this migration, not supplied at creation time.
3. Tighten the column to NOT NULL so future inserts (use case +
   repository) are forced to provide a real value.

Downgrade simply drops the column.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


_DUMMY_HOST_EMAIL = "glhf0825@gmail.com"


def upgrade() -> None:
    op.add_column(
        "leagues",
        sa.Column("host_email", sa.String(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE leagues SET host_email = :email WHERE host_email IS NULL"
        ).bindparams(email=_DUMMY_HOST_EMAIL)
    )
    op.alter_column("leagues", "host_email", nullable=False)


def downgrade() -> None:
    op.drop_column("leagues", "host_email")
