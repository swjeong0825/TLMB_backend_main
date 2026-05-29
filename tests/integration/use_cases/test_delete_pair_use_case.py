"""Integration tests for DeletePairUseCase."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.delete_pair_use_case import (
    DeletePairCommand,
    DeletePairUseCase,
)
from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import (
    LeagueNotFoundError,
    PairHasMatchesError,
    PairNotFoundError,
    UnauthorizedError,
)
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)
from app.infrastructure.persistence.repositories.match_repository import (
    SqlAlchemyMatchRepository,
)
from tests.integration.league_rules_fixtures import LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS


async def _setup(session: AsyncSession) -> tuple[League, str]:
    """Return (league, pair_alice_bob_id_str) — no matches attached."""
    league = League.create(
        "Delete Pair League",
        None,
        "host-del-tok",
        host_email="host@example.com",
        rules=LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS,
    )
    _, pair = league.register_players_and_pair("alice", "bob")
    league.register_players_and_pair("charlie", "diana")   # second pair
    await SqlAlchemyLeagueRepository(session).save(league)
    await session.commit()
    return league, str(pair.pair_id.value)


async def test_deletes_pair_successfully(session: AsyncSession) -> None:
    league, pair_id = await _setup(session)
    league_repo = SqlAlchemyLeagueRepository(session)
    match_repo = SqlAlchemyMatchRepository(session)

    await DeletePairUseCase(league_repo, match_repo).execute(
        DeletePairCommand(
            host_token="host-del-tok",
            league_id=str(league.league_id),
            pair_id=pair_id,
        )
    )
    await session.commit()
    session.expire_all()

    refreshed = await league_repo.get_by_id(league.league_id)
    pair_ids = {str(t.pair_id.value) for t in refreshed.pairs}
    assert pair_id not in pair_ids


async def test_raises_when_pair_has_matches(persisted_league_with_match: dict) -> None:
    """Fixture already submitted a match for alice+bob vs charlie+diana."""
    league = persisted_league_with_match["league"]
    alice_bob_pair = next(
        t for t in league.pairs
        if {t.player_id_1, t.player_id_2} <= {p.player_id for p in league.players
                                                if p.nickname.value in {"alice", "bob"}}
    )
    from tests.integration.conftest import _session_factory

    async with _session_factory() as s:
        with pytest.raises(PairHasMatchesError):
            await DeletePairUseCase(
                SqlAlchemyLeagueRepository(s),
                SqlAlchemyMatchRepository(s),
            ).execute(
                DeletePairCommand(
                    host_token="fixture-host-token",
                    league_id=str(league.league_id),
                    pair_id=str(alice_bob_pair.pair_id.value),
                )
            )


async def test_raises_for_wrong_token(session: AsyncSession) -> None:
    league, pair_id = await _setup(session)

    with pytest.raises(UnauthorizedError):
        await DeletePairUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeletePairCommand(
                host_token="wrong-token",
                league_id=str(league.league_id),
                pair_id=pair_id,
            )
        )


async def test_raises_for_unknown_pair(session: AsyncSession) -> None:
    league, _ = await _setup(session)

    with pytest.raises(PairNotFoundError):
        await DeletePairUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeletePairCommand(
                host_token="host-del-tok",
                league_id=str(league.league_id),
                pair_id="00000000-0000-0000-0000-000000000001",
            )
        )


async def test_raises_for_unknown_league(session: AsyncSession) -> None:
    with pytest.raises(LeagueNotFoundError):
        await DeletePairUseCase(
            SqlAlchemyLeagueRepository(session),
            SqlAlchemyMatchRepository(session),
        ).execute(
            DeletePairCommand(
                host_token="any",
                league_id="00000000-0000-0000-0000-000000000000",
                pair_id="00000000-0000-0000-0000-000000000001",
            )
        )
