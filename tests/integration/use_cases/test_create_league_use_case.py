"""Integration tests for CreateLeagueUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import DEFAULT_LEAGUE_TIMEZONE
from app.domain.exceptions import LeagueTitleAlreadyExistsError, InvalidLeagueRulesError
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


_HOST_EMAIL = "host@example.com"


async def test_creates_league_and_returns_ids(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand("Spring Open", host_email=_HOST_EMAIL, description=None)
    )

    assert result.league_id
    assert result.host_token
    assert len(result.league_id) == 36   # UUID
    assert len(result.host_token) == 36  # UUID


async def test_persists_league_to_db(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand(
            "Summer Cup", host_email="Host@Example.COM", description="Annual summer tournament"
        )
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId
    found = await repo.get_by_id(LeagueId.from_str(result.league_id))

    assert found is not None
    assert found.title == "Summer Cup"
    assert found.description == "Annual summer tournament"
    assert found.host_token.value == result.host_token
    assert found.host_email.value == "host@example.com"  # normalized
    assert found.league_timezone.value == DEFAULT_LEAGUE_TIMEZONE
    assert found.rules == LeagueRules.default_for_new_league()


async def test_persists_explicit_league_timezone(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand(
            "Timezone Cup",
            host_email=_HOST_EMAIL,
            description=None,
            league_timezone="Asia/Seoul",
        )
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId
    found = await repo.get_by_id(LeagueId.from_str(result.league_id))

    assert found is not None
    assert found.league_timezone.value == "Asia/Seoul"


async def test_persists_explicit_rules(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    custom = {
        "version": 8,
        "pair_matchup_idempotency": "none",
        "one_pair_per_player": True,
        "ranking_subject": "pair",
        "tie_breakers": ["matches_won"],
    }
    await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand(
            "Custom Rules League", host_email=_HOST_EMAIL, description=None, rules=custom
        )
    )
    await session.commit()
    session.expire_all()

    found = await repo.get_by_normalized_title("custom rules league")
    assert found is not None
    assert found.rules == LeagueRules.from_dict(custom)


async def test_invalid_rules_version_raises(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    with pytest.raises(InvalidLeagueRulesError):
        await CreateLeagueUseCase(repo).execute(
            CreateLeagueCommand(
                "Bad Rules League",
                host_email=_HOST_EMAIL,
                description=None,
                rules={
                    "version": 99,
                    "pair_matchup_idempotency": "none",
                    "one_pair_per_player": True,
                },
            )
        )


async def test_raises_for_duplicate_title(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    await use_case.execute(
        CreateLeagueCommand("Autumn League", host_email=_HOST_EMAIL, description=None)
    )

    with pytest.raises(LeagueTitleAlreadyExistsError):
        await use_case.execute(
            CreateLeagueCommand("Autumn League", host_email=_HOST_EMAIL, description=None)
        )


async def test_duplicate_check_is_case_insensitive(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    await use_case.execute(
        CreateLeagueCommand("Grand Slam", host_email=_HOST_EMAIL, description=None)
    )

    with pytest.raises(LeagueTitleAlreadyExistsError):
        await use_case.execute(
            CreateLeagueCommand("grand slam", host_email=_HOST_EMAIL, description=None)
        )


async def test_different_titles_both_succeed(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    r1 = await use_case.execute(
        CreateLeagueCommand("League A", host_email=_HOST_EMAIL, description=None)
    )
    r2 = await use_case.execute(
        CreateLeagueCommand("League B", host_email=_HOST_EMAIL, description=None)
    )

    assert r1.league_id != r2.league_id
    assert r1.host_token != r2.host_token


async def test_persists_league_and_seeded_initial_players_atomically(
    session: AsyncSession,
) -> None:
    """Seeding `initial_players` on create must reach the DB in the same
    transaction as the league row -- after a single commit, both queries
    succeed."""
    repo = SqlAlchemyLeagueRepository(session)
    result = await CreateLeagueUseCase(repo).execute(
        CreateLeagueCommand(
            "Seeded Roster League",
            host_email=_HOST_EMAIL,
            description=None,
            rules={
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": False,
            },
            initial_players=["Alex", "Daniel", "Jason"],
        )
    )
    await session.commit()
    session.expire_all()

    from app.domain.aggregates.league.value_objects import LeagueId

    found = await repo.get_by_id(LeagueId.from_str(result.league_id))
    assert found is not None
    assert found.rules.auto_register_players_on_match is False
    assert sorted(p.nickname.value for p in found.players) == [
        "alex",
        "daniel",
        "jason",
    ]
    assert found.pairs == []


async def test_duplicate_seeded_player_rejects_whole_creation(
    session: AsyncSession,
) -> None:
    """If the bootstrap list contains an in-batch duplicate, the aggregate
    raises before `save` -- the league itself must not be persisted."""
    from app.domain.exceptions import NicknameAlreadyInUseError

    repo = SqlAlchemyLeagueRepository(session)
    use_case = CreateLeagueUseCase(repo)

    with pytest.raises(NicknameAlreadyInUseError):
        await use_case.execute(
            CreateLeagueCommand(
                "Dup-Bootstrap League",
                host_email=_HOST_EMAIL,
                description=None,
                initial_players=["Alex", "ALEX"],
            )
        )
    await session.rollback()

    found = await repo.get_by_normalized_title("dup-bootstrap league")
    assert found is None
