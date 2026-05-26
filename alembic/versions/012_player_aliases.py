"""Add player aliases

Revision ID: 012
Revises: 011
Create Date: 2026-05-26

Creates `player_aliases`, backfills each existing player nickname as the
canonical alias, then removes `players.nickname_normalized`. Downgrade restores
only the canonical nickname to `players`; non-canonical aliases added after
upgrade are intentionally lost.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_aliases",
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alias_normalized", sa.String(), nullable=False),
        sa.Column(
            "is_canonical",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["player_id"],
            ["players.player_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("player_id", "alias_normalized"),
        sa.UniqueConstraint(
            "league_id",
            "alias_normalized",
            name="uq_player_aliases_league_alias",
        ),
    )
    op.create_index(
        "uq_player_aliases_canonical",
        "player_aliases",
        ["player_id"],
        unique=True,
        postgresql_where=sa.text("is_canonical"),
    )
    op.create_index(
        "ix_player_aliases_league_alias",
        "player_aliases",
        ["league_id", "alias_normalized"],
    )

    op.execute(
        "INSERT INTO player_aliases "
        "(player_id, league_id, alias_normalized, is_canonical) "
        "SELECT player_id, league_id, nickname_normalized, true FROM players"
    )

    op.drop_constraint("uq_players_league_nickname", "players", type_="unique")
    op.drop_column("players", "nickname_normalized")


def downgrade() -> None:
    op.add_column(
        "players",
        sa.Column("nickname_normalized", sa.String(), nullable=True),
    )
    op.execute(
        "UPDATE players p "
        "SET nickname_normalized = pa.alias_normalized "
        "FROM player_aliases pa "
        "WHERE pa.player_id = p.player_id AND pa.is_canonical"
    )
    op.alter_column("players", "nickname_normalized", nullable=False)
    op.create_unique_constraint(
        "uq_players_league_nickname",
        "players",
        ["league_id", "nickname_normalized"],
    )
    op.drop_index("ix_player_aliases_league_alias", table_name="player_aliases")
    op.drop_index("uq_player_aliases_canonical", table_name="player_aliases")
    op.drop_table("player_aliases")
