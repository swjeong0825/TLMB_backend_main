"""Integration tests for DeleteMatchUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.delete_match_use_case import (
    DeleteMatchCommand,
    DeleteMatchUseCase,
)
from app.domain.aggregates.match.value_objects import MatchId
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchNotFoundError,
    UnauthorizedError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)


async def test_deletes_match_successfully(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        await DeleteMatchUseCase(
            SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
        ).execute(
            DeleteMatchCommand(
                host_token="fixture-host-token",
                league_id=str(league.league_id),
                match_id=match_id,
            )
        )
        await s.commit()

    async with _session_factory() as s:
        matches = await SqlAlchemyMatchRepository(s).get_all_by_league(league.league_id)

    assert all(str(m.match_id.value) != match_id for m in matches)


async def test_raises_for_wrong_token(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        with pytest.raises(UnauthorizedError):
            await DeleteMatchUseCase(
                SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
            ).execute(
                DeleteMatchCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id=match_id,
                )
            )


async def test_raises_for_unknown_match(session: AsyncSession, persisted_league: object) -> None:
    from app.domain.aggregates.league.aggregate_root import League
    league: League = persisted_league  # type: ignore[assignment]

    with pytest.raises(MatchNotFoundError):
        await DeleteMatchUseCase(
            SqlAlchemyLeagueRepository(session), SqlAlchemyMatchRepository(session)
        ).execute(
            DeleteMatchCommand(
                host_token="fixture-host-token",
                league_id=str(league.league_id),
                match_id="00000000-0000-0000-0000-000000000001",
            )
        )


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await DeleteMatchUseCase(
            SqlAlchemyLeagueRepository(session), SqlAlchemyMatchRepository(session)
        ).execute(
            DeleteMatchCommand(
                host_token="any",
                league_id="00000000-0000-0000-0000-000000000000",
                match_id="00000000-0000-0000-0000-000000000001",
            )
        )
