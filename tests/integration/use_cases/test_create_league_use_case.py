"""Integration tests for CreateLeagueUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.domain.exceptions import LeagueTitleAlreadyExistsError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


async def test_creates_league_and_returns_ids(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(CreateLeagueCommand("Spring Open", None))

    assert result.league_id
    assert result.host_token
    assert len(result.league_id) == 36   # UUID
    assert len(result.host_token) == 36  # UUID


async def test_persists_league_to_db(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand("Summer Cup", "Annual summer tournament")
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId
    found = await repo.get_by_id(LeagueId.from_str(result.league_id))

    assert found is not None
    assert found.title == "Summer Cup"
    assert found.description == "Annual summer tournament"
    assert found.host_token.value == result.host_token


async def test_raises_for_duplicate_title(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    await use_case.execute(CreateLeagueCommand("Autumn League", None))

    with pytest.raises(LeagueTitleAlreadyExistsError):
        await use_case.execute(CreateLeagueCommand("Autumn League", None))


async def test_duplicate_check_is_case_insensitive(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    await use_case.execute(CreateLeagueCommand("Grand Slam", None))

    with pytest.raises(LeagueTitleAlreadyExistsError):
        await use_case.execute(CreateLeagueCommand("grand slam", None))


async def test_different_titles_both_succeed(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    r1 = await use_case.execute(CreateLeagueCommand("League A", None))
    r2 = await use_case.execute(CreateLeagueCommand("League B", None))

    assert r1.league_id != r2.league_id
    assert r1.host_token != r2.host_token
