from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.config.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeagueORM(Base):
    __tablename__ = "leagues"

    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    title_normalized: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    host_token: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    players: Mapped[list[PlayerORM]] = relationship(
        "PlayerORM", back_populates="league", cascade="all, delete-orphan"
    )
    teams: Mapped[list[TeamORM]] = relationship(
        "TeamORM", back_populates="league", cascade="all, delete-orphan"
    )
    matches: Mapped[list[MatchORM]] = relationship(
        "MatchORM", back_populates="league"
    )


class PlayerORM(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("league_id", "nickname_normalized", name="uq_players_league_nickname"),
        Index("ix_players_league_id", "league_id"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.league_id", ondelete="CASCADE"),
        nullable=False,
    )
    nickname_normalized: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="players")


class TeamORM(Base):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("league_id", "player_id_1", "player_id_2", name="uq_teams_league_players"),
        Index("ix_teams_league_id", "league_id"),
    )

    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.league_id", ondelete="CASCADE"),
        nullable=False,
    )
    player_id_1: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.player_id"),
        nullable=False,
    )
    player_id_2: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.player_id"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="teams")


class MatchORM(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_league_created", "league_id", "created_at"),
        Index("ix_matches_team1_id", "team1_id"),
        Index("ix_matches_team2_id", "team2_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.league_id"),
        nullable=False,
    )
    team1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.team_id"),
        nullable=False,
    )
    team2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("teams.team_id"),
        nullable=False,
    )
    team1_score: Mapped[str] = mapped_column(String, nullable=False)
    team2_score: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="matches")
