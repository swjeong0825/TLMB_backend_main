"""Integration tests for CreateLeagueUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import LeagueTitleAlreadyExistsError, InvalidLeagueRulesError
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
    assert found.rules == LeagueRules.default_for_new_league()


async def test_persists_explicit_rules(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    custom = {
        "version": 1,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
    }
    await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand("Custom Rules League", None, rules=custom)
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId

    found = await repo.get_by_normalized_title("custom rules league")
    assert found is not None
    assert found.rules == LeagueRules.from_dict(custom)


async def test_invalid_rules_version_raises(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    with pytest.raises(InvalidLeagueRulesError):
        await CreateLeagueUseCase(repo).execute(
            CreateLeagueCommand(
                "Bad Rules League",
                None,
                rules={
                    "version": 99,
                    "match_pair_idempotency": "none",
                    "one_team_per_player": True,
                },
            )
        )


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


async def test_persists_league_and_seeded_allowlist_atomically(
    session: AsyncSession,
) -> None:
    """Seeding `allowlist` on create must reach the DB in the same
    transaction as the league row — after a single commit, both queries
    succeed."""
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand(
            "Seeded Allowlist League",
            None,
            rules={
                "version": 5,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_allowlist": True,
            },
            allowlist=["Alex", "Daniel", "Jason"],
        )
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId

    found = await repo.get_by_id(LeagueId.from_str(result.league_id))
    assert found is not None
    assert found.rules.require_allowlist is True
    assert sorted(entry.nickname.value for entry in found.allowlist) == [
        "alex",
        "daniel",
        "jason",
    ]


async def test_duplicate_seeded_allowlist_entry_rejects_whole_creation(
    session: AsyncSession,
) -> None:
    """If the bootstrap list contains an in-batch duplicate, the aggregate
    raises before `save` — the league itself must not be persisted."""
    from app.domain.exceptions import AllowlistNicknameAlreadyExistsError

    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    with pytest.raises(AllowlistNicknameAlreadyExistsError):
        await use_case.execute(
            CreateLeagueCommand(
                "Dup-Bootstrap League",
                None,
                allowlist=["Alex", "ALEX"],
            )
        )
    await session.rollback()

    found = await repo.get_by_normalized_title("dup-bootstrap league")
    assert found is None
