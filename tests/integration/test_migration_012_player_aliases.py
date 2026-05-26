"""Behavior test for alembic 012 (player_aliases).

The integration database is already at HEAD, so this verifies the post-migration
shape that 012 guarantees: player names live in `player_aliases`, each player
has one canonical alias row, and the legacy `players.nickname_normalized`
column is gone.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


async def test_player_aliases_table_holds_canonical_names(
    session: AsyncSession,
) -> None:
    league = League.create(
        "Alias Migration Shape",
        None,
        "fixture-host-token",
        host_email="host@example.com",
    )
    league.add_players(["alice", "bob"])
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()

    rows = await session.execute(
        text(
            "SELECT alias_normalized, is_canonical "
            "FROM player_aliases "
            "WHERE league_id = :league_id "
            "ORDER BY alias_normalized"
        ),
        {"league_id": league.league_id.value},
    )

    assert rows.all() == [("alice", True), ("bob", True)]


async def test_players_table_no_longer_has_nickname_normalized(
    session: AsyncSession,
) -> None:
    result = await session.execute(
        text(
            "SELECT column_name "
            "FROM information_schema.columns "
            "WHERE table_name = 'players' "
            "AND column_name = 'nickname_normalized'"
        )
    )

    assert result.all() == []
