"""Integration tests for EditMatchScoreUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.domain.exceptions import (
    InvalidSetScoreError,
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


async def test_updates_match_score(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        result = await EditMatchScoreUseCase(
            SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
        ).execute(
            EditMatchScoreCommand(
                host_token="fixture-host-token",
                league_id=str(league.league_id),
                match_id=match_id,
                team1_score="3",
                team2_score="6",
            )
        )

    assert result.match_id == match_id
    assert result.team1_score == "3"
    assert result.team2_score == "6"


async def test_new_score_persisted_to_db(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory, _engine
    from app.domain.aggregates.match.value_objects import MatchId

    async with _session_factory() as s:
        await EditMatchScoreUseCase(
            SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
        ).execute(
            EditMatchScoreCommand(
                host_token="fixture-host-token",
                league_id=str(league.league_id),
                match_id=match_id,
                team1_score="0",
                team2_score="6",
            )
        )
        await s.commit()

    async with _session_factory() as s:
        updated = await SqlAlchemyMatchRepository(s).get_by_id(
            MatchId.from_str(match_id), league.league_id
        )

    assert updated.set_score.team1_score == "0"
    assert updated.set_score.team2_score == "6"


async def test_raises_for_wrong_token(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        with pytest.raises(UnauthorizedError):
            await EditMatchScoreUseCase(
                SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
            ).execute(
                EditMatchScoreCommand(
                    host_token="wrong-token",
                    league_id=str(league.league_id),
                    match_id=match_id,
                    team1_score="3",
                    team2_score="6",
                )
            )


async def test_raises_for_invalid_score(persisted_league_with_match: dict) -> None:
    league = persisted_league_with_match["league"]
    match_id = persisted_league_with_match["match_id"]
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        with pytest.raises(InvalidSetScoreError):
            await EditMatchScoreUseCase(
                SqlAlchemyLeagueRepository(s), SqlAlchemyMatchRepository(s)
            ).execute(
                EditMatchScoreCommand(
                    host_token="fixture-host-token",
                    league_id=str(league.league_id),
                    match_id=match_id,
                    team1_score="abc",
                    team2_score="6",
                )
            )


async def test_raises_for_unknown_match(session: AsyncSession, persisted_league: object) -> None:
    from app.domain.aggregates.league.aggregate_root import League
    league: League = persisted_league  # type: ignore[assignment]

    with pytest.raises(MatchNotFoundError):
        await EditMatchScoreUseCase(
            SqlAlchemyLeagueRepository(session), SqlAlchemyMatchRepository(session)
        ).execute(
            EditMatchScoreCommand(
                host_token="fixture-host-token",
                league_id=str(league.league_id),
                match_id="00000000-0000-0000-0000-000000000001",
                team1_score="6",
                team2_score="3",
            )
        )


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await EditMatchScoreUseCase(
            SqlAlchemyLeagueRepository(session), SqlAlchemyMatchRepository(session)
        ).execute(
            EditMatchScoreCommand(
                host_token="any",
                league_id="00000000-0000-0000-0000-000000000000",
                match_id="00000000-0000-0000-0000-000000000001",
                team1_score="6",
                team2_score="3",
            )
        )
