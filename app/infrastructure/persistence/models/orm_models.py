from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.aggregates.league.value_objects import DEFAULT_LEAGUE_TIMEZONE
from app.infrastructure.config.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LeagueORM(Base):
    __tablename__ = "leagues"

    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, nullable=False)
    title_normalized: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    host_token: Mapped[str] = mapped_column(String, nullable=False)
    host_email: Mapped[str] = mapped_column(String, nullable=False)
    league_timezone: Mapped[str] = mapped_column(
        String,
        nullable=False,
        server_default=DEFAULT_LEAGUE_TIMEZONE,
    )
    latest_match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    players: Mapped[list[PlayerORM]] = relationship(
        "PlayerORM", back_populates="league", cascade="all, delete-orphan"
    )
    pairs: Mapped[list[PairORM]] = relationship(
        "PairORM", back_populates="league", cascade="all, delete-orphan"
    )
    matches: Mapped[list[MatchORM]] = relationship(
        "MatchORM", back_populates="league"
    )


class PlayerORM(Base):
    __tablename__ = "players"
    __table_args__ = (
        Index("ix_players_league_id", "league_id"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.league_id", ondelete="CASCADE"),
        nullable=False,
    )
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="players")
    aliases: Mapped[list[PlayerAliasORM]] = relationship(
        "PlayerAliasORM",
        back_populates="player",
        cascade="all, delete-orphan",
        order_by=lambda: (
            PlayerAliasORM.is_canonical.desc(),
            PlayerAliasORM.created_at.asc(),
            PlayerAliasORM.alias_normalized.asc(),
        ),
    )


class PlayerAliasORM(Base):
    __tablename__ = "player_aliases"
    __table_args__ = (
        UniqueConstraint(
            "league_id",
            "alias_normalized",
            name="uq_player_aliases_league_alias",
        ),
        Index(
            "uq_player_aliases_canonical",
            "player_id",
            unique=True,
            postgresql_where=text("is_canonical"),
        ),
        Index("ix_player_aliases_league_alias", "league_id", "alias_normalized"),
    )

    player_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("players.player_id", ondelete="CASCADE"),
        primary_key=True,
    )
    league_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    alias_normalized: Mapped[str] = mapped_column(String, primary_key=True)
    is_canonical: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    player: Mapped[PlayerORM] = relationship("PlayerORM", back_populates="aliases")


class PairORM(Base):
    __tablename__ = "pairs"
    __table_args__ = (
        UniqueConstraint("league_id", "player_id_1", "player_id_2", name="uq_pairs_league_players"),
        Index("ix_pairs_league_id", "league_id"),
    )

    pair_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="pairs")


class MatchORM(Base):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_league_created", "league_id", "created_at"),
        Index("ix_matches_pair1_id", "pair1_id"),
        Index("ix_matches_pair2_id", "pair2_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leagues.league_id"),
        nullable=False,
    )
    pair1_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pairs.pair_id"),
        nullable=False,
    )
    pair2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pairs.pair_id"),
        nullable=False,
    )
    pair1_score: Mapped[str] = mapped_column(String, nullable=False)
    pair2_score: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_utcnow, nullable=False
    )

    league: Mapped[LeagueORM] = relationship("LeagueORM", back_populates="matches")
