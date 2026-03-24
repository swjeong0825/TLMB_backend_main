"""Integration tests for EditPlayerNicknameUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.edit_player_nickname_use_case import (
    EditPlayerNicknameCommand,
    EditPlayerNicknameUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import (
    LeagueNotFoundError,
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    UnauthorizedError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


async def _setup_league_with_players(session: AsyncSession) -> tuple[League, str, str]:
    """Return (league, alice_player_id, bob_player_id)."""
    league = League.create("Edit Nick League", None, "host-token-edit")
    new_players, _ = league.register_players_and_team("alice", "bob")
    alice_id = str(new_players[0].player_id.value)
    bob_id = str(new_players[1].player_id.value)
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()
    return league, alice_id, bob_id


async def test_updates_player_nickname(session: AsyncSession) -> None:
    league, alice_id, _ = await _setup_league_with_players(session)
    repo = SqlAlchemyLeagueRepository(session)

    result = await EditPlayerNicknameUseCase(repo).execute(
        EditPlayerNicknameCommand(
            host_token="host-token-edit",
            league_id=str(league.league_id),
            player_id=alice_id,
            new_nickname="Serena",
        )
    )

    assert result.player_id == alice_id
    assert result.new_nickname == "serena"   # normalized to lowercase


async def test_new_nickname_persisted_to_db(session: AsyncSession) -> None:
    league, alice_id, _ = await _setup_league_with_players(session)
    repo = SqlAlchemyLeagueRepository(session)

    await EditPlayerNicknameUseCase(repo).execute(
        EditPlayerNicknameCommand(
            host_token="host-token-edit",
            league_id=str(league.league_id),
            player_id=alice_id,
            new_nickname="Venus",
        )
    )
    await session.commit()
    session.expire_all()

    refreshed = await repo.get_by_id(league.league_id)
    nicknames = {p.nickname.value for p in refreshed.players}
    assert "venus" in nicknames
    assert "alice" not in nicknames


async def test_raises_for_wrong_token(session: AsyncSession) -> None:
    league, alice_id, _ = await _setup_league_with_players(session)

    with pytest.raises(UnauthorizedError):
        await EditPlayerNicknameUseCase(SqlAlchemyLeagueRepository(session)).execute(
            EditPlayerNicknameCommand(
                host_token="wrong-token",
                league_id=str(league.league_id),
                player_id=alice_id,
                new_nickname="Serena",
            )
        )


async def test_raises_for_unknown_player(session: AsyncSession) -> None:
    league, _, _ = await _setup_league_with_players(session)

    with pytest.raises(PlayerNotFoundError):
        await EditPlayerNicknameUseCase(SqlAlchemyLeagueRepository(session)).execute(
            EditPlayerNicknameCommand(
                host_token="host-token-edit",
                league_id=str(league.league_id),
                player_id="00000000-0000-0000-0000-000000000001",
                new_nickname="Serena",
            )
        )


async def test_raises_for_duplicate_nickname(session: AsyncSession) -> None:
    league, alice_id, _ = await _setup_league_with_players(session)

    with pytest.raises(NicknameAlreadyInUseError):
        await EditPlayerNicknameUseCase(SqlAlchemyLeagueRepository(session)).execute(
            EditPlayerNicknameCommand(
                host_token="host-token-edit",
                league_id=str(league.league_id),
                player_id=alice_id,
                new_nickname="bob",   # already taken
            )
        )


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await EditPlayerNicknameUseCase(SqlAlchemyLeagueRepository(session)).execute(
            EditPlayerNicknameCommand(
                host_token="any",
                league_id="00000000-0000-0000-0000-000000000000",
                player_id="00000000-0000-0000-0000-000000000001",
                new_nickname="Serena",
            )
        )
