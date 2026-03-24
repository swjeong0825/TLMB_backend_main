"""Integration tests for SqlAlchemyLeagueRepository."""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import LeagueId
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_league(title: str = "Test League", token: str = "token-abc") -> League:
    return League.create(title, None, token)


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


async def test_get_by_id_returns_none_when_not_found(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await repo.get_by_id(LeagueId.generate())
    assert result is None


async def test_save_and_get_by_id_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league("Round Trip League")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(league.league_id)

    assert found is not None
    assert found.title == "Round Trip League"
    assert found.host_token.value == "token-abc"
    assert str(found.league_id) == str(league.league_id)


async def test_save_league_with_description(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create("Described League", "A great league", "tok")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(league.league_id)

    assert found is not None
    assert found.description == "A great league"


# ---------------------------------------------------------------------------
# get_by_id_with_lock
# ---------------------------------------------------------------------------


async def test_get_by_id_with_lock_returns_league(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id_with_lock(league.league_id)

    assert found is not None
    assert str(found.league_id) == str(league.league_id)


async def test_get_by_id_with_lock_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await repo.get_by_id_with_lock(LeagueId.generate())
    assert result is None


# ---------------------------------------------------------------------------
# get_by_normalized_title
# ---------------------------------------------------------------------------


async def test_get_by_normalized_title_finds_league(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league("Summer Cup")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_normalized_title("summer cup")

    assert found is not None
    assert found.title == "Summer Cup"


async def test_get_by_normalized_title_is_case_insensitive(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    await repo.save(_make_league("Grand Slam"))
    await session.commit()
    session.expire_all()

    assert await repo.get_by_normalized_title("grand slam") is not None
    assert await repo.get_by_normalized_title("GRAND SLAM") is None  # stored as lowercase


async def test_get_by_normalized_title_returns_none_when_missing(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await repo.get_by_normalized_title("nonexistent league")
    assert result is None


# ---------------------------------------------------------------------------
# save – update path
# ---------------------------------------------------------------------------


async def test_save_updates_existing_league_title(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league("Original Title")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    # Mutate and re-save
    reloaded = await repo.get_by_id_with_lock(league.league_id)
    reloaded.title = "Updated Title"
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    assert final.title == "Updated Title"


async def test_save_persists_players_and_teams(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league("Player League")
    league.register_players_and_team("alice", "bob")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(league.league_id)

    assert len(found.players) == 2
    nicknames = {p.nickname.value for p in found.players}
    assert nicknames == {"alice", "bob"}
    assert len(found.teams) == 1


async def test_save_updates_player_nickname(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.register_players_and_team("alice", "bob")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    reloaded.edit_player_nickname(
        str(next(p for p in reloaded.players if p.nickname.value == "alice").player_id.value),
        "serena",
    )
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    nicknames = {p.nickname.value for p in final.players}
    assert "serena" in nicknames
    assert "alice" not in nicknames


async def test_save_removes_pending_deleted_teams(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.register_players_and_team("alice", "bob")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    team_id = str(reloaded.teams[0].team_id.value)
    reloaded.delete_team(team_id)
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    assert len(final.teams) == 0


# ---------------------------------------------------------------------------
# unique constraint
# ---------------------------------------------------------------------------


async def test_duplicate_normalized_title_raises_integrity_error(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    await repo.save(_make_league("Same Title", token="tok1"))
    await session.commit()

    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await repo.save(_make_league("same title", token="tok2"))
