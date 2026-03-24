"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-01-01 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "leagues",
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("title_normalized", sa.String(), nullable=False),
        sa.Column("host_token", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
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
        sa.PrimaryKeyConstraint("league_id"),
        sa.UniqueConstraint("title_normalized", name="uq_leagues_title_normalized"),
    )

    op.create_table(
        "players",
        sa.Column("player_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.PrimaryKeyConstraint("player_id"),
        sa.UniqueConstraint(
            "league_id",
            "nickname_normalized",
            name="uq_players_league_nickname",
        ),
    )
    op.create_index("ix_players_league_id", "players", ["league_id"])

    op.create_table(
        "teams",
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id_1", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("player_id_2", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["player_id_1"], ["players.player_id"]),
        sa.ForeignKeyConstraint(["player_id_2"], ["players.player_id"]),
        sa.PrimaryKeyConstraint("team_id"),
        sa.UniqueConstraint(
            "league_id",
            "player_id_1",
            "player_id_2",
            name="uq_teams_league_players",
        ),
    )
    op.create_index("ix_teams_league_id", "teams", ["league_id"])

    op.create_table(
        "matches",
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("league_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team1_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team2_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team1_score", sa.String(), nullable=False),
        sa.Column("team2_score", sa.String(), nullable=False),
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
        sa.ForeignKeyConstraint(["league_id"], ["leagues.league_id"]),
        sa.ForeignKeyConstraint(["team1_id"], ["teams.team_id"]),
        sa.ForeignKeyConstraint(["team2_id"], ["teams.team_id"]),
        sa.PrimaryKeyConstraint("match_id"),
    )
    op.create_index(
        "ix_matches_league_created", "matches", ["league_id", "created_at"]
    )
    op.create_index("ix_matches_team1_id", "matches", ["team1_id"])
    op.create_index("ix_matches_team2_id", "matches", ["team2_id"])


def downgrade() -> None:
    op.drop_index("ix_matches_team2_id", table_name="matches")
    op.drop_index("ix_matches_team1_id", table_name="matches")
    op.drop_index("ix_matches_league_created", table_name="matches")
    op.drop_table("matches")

    op.drop_index("ix_teams_league_id", table_name="teams")
    op.drop_table("teams")

    op.drop_index("ix_players_league_id", table_name="players")
    op.drop_table("players")

    op.drop_table("leagues")
