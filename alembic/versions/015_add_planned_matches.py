"""Add league-scoped planned matches.

Revision ID: 015
Revises: 014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "planned_matches",
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("league_id", "id"),
        sa.ForeignKeyConstraint(["league_id"], ["leagues.league_id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("planned_matches")
