"""Integration tests for SqlAlchemyLeagueRepository — eligible_players persistence path.

Covers the round-trip and save-side flows that landed with v4:
- New EligiblePlayer rows added through the aggregate are INSERTed by save().
- Subsequent get_by_id reload exposes them via league.eligible_players.
- Removed EligiblePlayer ids in pending_deleted_eligible_player_ids are
  DELETEed by save().
- Saving a league twice without changes does not create duplicates.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


def _make_league(title: str = "Eligible Test League", token: str = "tok") -> League:
    return League.create(title, None, token)


async def test_save_persists_added_eligible_players(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    await repo.save(league)
    await session.commit()
    session.expire_all()

    league = await repo.get_by_id(league.league_id)
    assert league is not None

    league.add_eligible_players(["alex", "daniel", "jason"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    nicks = {ep.nickname.value for ep in reloaded.eligible_players}
    assert nicks == {"alex", "daniel", "jason"}


async def test_eligible_player_ids_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    added = league.add_eligible_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    reloaded_ids = {ep.eligible_player_id.value for ep in reloaded.eligible_players}
    assert reloaded_ids == {a.eligible_player_id.value for a in added}


async def test_save_removes_pending_deleted_eligible_players(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    added = league.add_eligible_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    league = await repo.get_by_id(league.league_id)
    assert league is not None

    target = next(
        ep for ep in league.eligible_players if ep.nickname.value == "alex"
    )
    league.remove_eligible_player(str(target.eligible_player_id.value))
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    nicks = {ep.nickname.value for ep in reloaded.eligible_players}
    assert nicks == {"daniel"}


async def test_resave_without_changes_does_not_duplicate(
    session: AsyncSession,
) -> None:
    """Save mirrors the existing players/teams pattern: existing rows are
    detected via get-by-PK before insert, so re-save is a no-op for unchanged
    aggregates."""
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    league.add_eligible_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    assert final is not None
    assert len(final.eligible_players) == 2


async def test_eligible_players_independent_of_roster_persistence(
    session: AsyncSession,
) -> None:
    """A nickname can live in eligible_players without ever having been
    promoted to a roster Player row (the two tables have no FK relationship)."""
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    league.add_eligible_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    assert reloaded.players == []
    assert reloaded.teams == []
    assert {ep.nickname.value for ep in reloaded.eligible_players} == {"alex", "daniel"}


async def test_v4_rules_round_trip_with_require_eligible_players_true(
    session: AsyncSession,
) -> None:
    """A league created with require_eligible_players=true round-trips through
    the JSONB column, and reloads as `LeagueRules.require_eligible_players=True`."""
    from app.domain.aggregates.league.league_rules import LeagueRules

    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
    )
    league = League.create("Rules V4 League", None, "tok", rules=rules)

    repo = SqlAlchemyLeagueRepository(session)
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    assert reloaded.rules.version == 4
    assert reloaded.rules.require_eligible_players is True
