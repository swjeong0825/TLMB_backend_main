"""Integration tests for SqlAlchemyLeagueRepository — allowlist persistence path.

Covers the round-trip and save-side flows for the allowlist feature:
- New AllowlistEntry rows added through the aggregate are INSERTed by save().
- Subsequent get_by_id reload exposes them via league.allowlist.
- Removed AllowlistEntry ids in pending_deleted_allowlist_entry_ids are
  DELETEed by save().
- Saving a league twice without changes does not create duplicates.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


def _make_league(title: str = "Allowlist Test League", token: str = "tok") -> League:
    return League.create(title, None, token)


async def test_save_persists_added_allowlist_entries(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    await repo.save(league)
    await session.commit()
    session.expire_all()

    league = await repo.get_by_id(league.league_id)
    assert league is not None

    league.add_allowlist_entries(["alex", "daniel", "jason"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    nicks = {entry.nickname.value for entry in reloaded.allowlist}
    assert nicks == {"alex", "daniel", "jason"}


async def test_allowlist_entry_ids_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    added = league.add_allowlist_entries(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    reloaded_ids = {entry.allowlist_entry_id.value for entry in reloaded.allowlist}
    assert reloaded_ids == {a.allowlist_entry_id.value for a in added}


async def test_save_removes_pending_deleted_allowlist_entries(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    added = league.add_allowlist_entries(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    league = await repo.get_by_id(league.league_id)
    assert league is not None

    target = next(
        entry for entry in league.allowlist if entry.nickname.value == "alex"
    )
    league.remove_allowlist_entry(str(target.allowlist_entry_id.value))
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    nicks = {entry.nickname.value for entry in reloaded.allowlist}
    assert nicks == {"daniel"}


async def test_resave_without_changes_does_not_duplicate(
    session: AsyncSession,
) -> None:
    """Save mirrors the existing players/teams pattern: existing rows are
    detected via get-by-PK before insert, so re-save is a no-op for unchanged
    aggregates."""
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    league.add_allowlist_entries(["alex", "daniel"])
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
    assert len(final.allowlist) == 2


async def test_allowlist_independent_of_roster_persistence(
    session: AsyncSession,
) -> None:
    """A nickname can live in the allowlist without ever having been promoted
    to a roster Player row (the two tables have no FK relationship)."""
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    league.add_allowlist_entries(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    assert reloaded.players == []
    assert reloaded.teams == []
    assert {entry.nickname.value for entry in reloaded.allowlist} == {"alex", "daniel"}


async def test_v5_rules_round_trip_with_require_allowlist_true(
    session: AsyncSession,
) -> None:
    """A league created with require_allowlist=true round-trips through the
    JSONB column, and reloads as `LeagueRules.require_allowlist=True`."""
    from app.domain.aggregates.league.league_rules import LeagueRules

    rules = LeagueRules.from_dict(
        {
            "version": 5,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
        }
    )
    league = League.create("Rules V5 League", None, "tok", rules=rules)

    repo = SqlAlchemyLeagueRepository(session)
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    assert reloaded.rules.version == 5
    assert reloaded.rules.require_allowlist is True
