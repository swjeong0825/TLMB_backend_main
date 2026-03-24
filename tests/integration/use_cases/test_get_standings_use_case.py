"""Integration tests for GetStandingsUseCase."""
from __future__ import annotations

from functools import partial

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.get_standings_use_case import (
    GetStandingsQuery,
    GetStandingsUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import LeagueNotFoundError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)


async def test_returns_empty_standings_for_league_with_no_matches(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = League.create("Empty League", None, "tok")
    await repo.save(league)

    use_case = GetStandingsUseCase(repo, SqlAlchemyMatchRepository(session))
    entries = await use_case.execute(GetStandingsQuery(league_id=str(league.league_id)))

    assert entries == []


async def test_returns_correct_standings_after_match(persisted_league_with_match: dict) -> None:
    """Use the conftest fixture that already submitted alice+bob vs charlie+diana 6-3."""
    league = persisted_league_with_match["league"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        league_repo = SqlAlchemyLeagueRepository(s)
        match_repo = SqlAlchemyMatchRepository(s)
        entries = await GetStandingsUseCase(league_repo, match_repo).execute(
            GetStandingsQuery(league_id=str(league.league_id))
        )

    assert len(entries) == 2
    assert entries[0].rank == 1
    assert entries[0].wins == 1
    assert entries[0].losses == 0
    assert entries[1].rank == 2
    assert entries[1].wins == 0
    assert entries[1].losses == 1


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    use_case = GetStandingsUseCase(
        SqlAlchemyLeagueRepository(session),
        SqlAlchemyMatchRepository(session),
    )
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(GetStandingsQuery(league_id="00000000-0000-0000-0000-000000000000"))
