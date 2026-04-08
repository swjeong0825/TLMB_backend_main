"""Integration tests for DeleteTeamUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.delete_team_use_case import (
    DeleteTeamCommand,
    DeleteTeamUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import (
    LeagueNotFoundError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS


async def _setup(session: AsyncSession) -> tuple[League, str]:
    """Return (league, team_alice_bob_id_str) — no matches attached."""
    league = League.create(
        "Delete Team League",
        None,
        "host-del-tok",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS,
    )
    _, team = league.register_players_and_team("alice", "bob")
    league.register_players_and_team("charlie", "diana")   # second team
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()
    return league, str(team.team_id.value)


async def test_deletes_team_successfully(session: AsyncSession) -> None:
    league, team_id = await _setup(session)
    league_repo = SqlAlchemyLeagueRepository(session)
    match_repo = SqlAlchemyMatchRepository(session)

    await DeleteTeamUseCase(league_repo, match_repo).execute(
        DeleteTeamCommand(
            host_token="host-del-tok",
            league_id=str(league.league_id),
            team_id=team_id,
        )
    )
    await session.commit()
    session.expire_all()

    refreshed = await league_repo.get_by_id(league.league_id)
    team_ids = {str(t.team_id.value) for t in refreshed.teams}
    assert team_id not in team_ids


async def test_raises_when_team_has_matches(persisted_league_with_match: dict) -> None:
    """Fixture already submitted a match for alice+bob vs charlie+diana."""
    league = persisted_league_with_match["league"]
    alice_bob_team = next(
        t for t in league.teams
        if {t.player_id_1, t.player_id_2} <= {p.player_id for p in league.players
                                                if p.nickname.value in {"alice", "bob"}}
    )
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        with pytest.raises(TeamHasMatchesError):
            await DeleteTeamUseCase(
                SqlAlchemyLeagueRepository(s),
                SqlAlchemyMatchRepository(s),
            ).execute(
                DeleteTeamCommand(
                    host_token="fixture-host-token",
                    league_id=str(league.league_id),
                    team_id=str(alice_bob_team.team_id.value),
                )
            )


async def test_raises_for_wrong_token(session: AsyncSession) -> None:
    league, team_id = await _setup(session)

    with pytest.raises(UnauthorizedError):
        await DeleteTeamUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeleteTeamCommand(
                host_token="wrong-token",
                league_id=str(league.league_id),
                team_id=team_id,
            )
        )


async def test_raises_for_unknown_team(session: AsyncSession) -> None:
    league, _ = await _setup(session)

    with pytest.raises(TeamNotFoundError):
        await DeleteTeamUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeleteTeamCommand(
                host_token="host-del-tok",
                league_id=str(league.league_id),
                team_id="00000000-0000-0000-0000-000000000001",
            )
        )


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await DeleteTeamUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeleteTeamCommand(
                host_token="any",
                league_id="00000000-0000-0000-0000-000000000000",
                team_id="00000000-0000-0000-0000-000000000001",
            )
        )
