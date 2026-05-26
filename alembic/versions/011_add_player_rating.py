"""Add optional player rating

Revision ID: 011
Revises: 010
Create Date: 2026-05-26

Adds nullable `players.rating` for host-curated player metadata. Existing
players stay unrated (`NULL`) until an admin sets a value.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("rating", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "rating")
