"""Integration tests for SqlAlchemyLeagueRepository — roster persistence path.

Covers the round-trip and save-side flows for roster pre-registration
(the v6 replacement for the v5 allowlist):

- New Player rows added through `League.add_players` are INSERTed by save().
- Subsequent get_by_id reload exposes them via league.players.
- Player ids in `pending_deleted_player_ids` are hard-deleted from `players`.
- Match-participation counts are surfaced onto `Player.match_count` at
  load time so `remove_player` can enforce its zero-participation guard.
- The new v6 rules JSONB round-trips with `auto_register_players_on_match`.
"""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import PlayerNickname
from app.infrastructure.persistence.repositories.league_repository import (
    SqlAlchemyLeagueRepository,
)


def _make_league(title: str = "Roster League", token: str = "tok") -> League:
    return League.create(title, None, token, host_email="host@example.com")


async def test_save_persists_added_players(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.add_players(["alex", "daniel", "jason"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)

    assert reloaded is not None
    assert len(reloaded.players) == 3
    nicks = {p.nickname.value for p in reloaded.players}
    assert nicks == {"alex", "daniel", "jason"}


async def test_player_rating_round_trips(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.add_players(["alex", "daniel"], ratings=[3.5, None])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)

    assert reloaded is not None
    ratings = {p.nickname.value: p.rating for p in reloaded.players}
    assert ratings == {"alex": 3.5, "daniel": None}


async def test_player_aliases_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    alex = league.add_players(["alex"])[0]
    league.add_alias_to_player(str(alex.player_id.value), "Lex")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)

    assert reloaded is not None
    player = next(p for p in reloaded.players if p.nickname.value == "alex")
    assert [a.value for a in player.aliases] == ["lex"]
    assert player.has_nickname(player.aliases[0])


async def test_save_promotes_alias_to_canonical_and_discards_old_canonical(
    session: AsyncSession,
) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    alex = league.add_players(["alex"])[0]
    league.add_alias_to_player(str(alex.player_id.value), "lex")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    player = next(p for p in reloaded.players if p.nickname.value == "alex")
    reloaded.edit_player_nickname(str(player.player_id.value), "lex")
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    final_player = next(p for p in final.players if p.nickname.value == "lex")
    assert final_player.aliases == []
    assert not final_player.has_nickname(PlayerNickname("alex"))


async def test_save_removes_alias(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    alex = league.add_players(["alex"])[0]
    league.add_alias_to_player(str(alex.player_id.value), "lex")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    player = next(p for p in reloaded.players if p.nickname.value == "alex")
    reloaded.remove_alias_from_player(str(player.player_id.value), "lex")
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    final_player = next(p for p in final.players if p.nickname.value == "alex")
    assert final_player.aliases == []


async def test_player_ids_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    added = league.add_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    reloaded_ids = {p.player_id.value for p in reloaded.players}
    assert reloaded_ids == {p.player_id.value for p in added}


async def test_save_removes_pending_deleted_players(session: AsyncSession) -> None:
    """`remove_player` queues the player id; save() must hard-delete it."""
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.add_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    target = next(p for p in reloaded.players if p.nickname.value == "alex")
    reloaded.remove_player(str(target.player_id.value))
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    assert len(final.players) == 1
    nicks = {p.nickname.value for p in final.players}
    assert nicks == {"daniel"}


async def test_repeated_add_then_save_is_idempotent_at_db_level(
    session: AsyncSession,
) -> None:
    """Re-saving a league whose players are already persisted must not
    duplicate rows (PK collision would surface as an IntegrityError otherwise)."""
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.add_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    assert len(final.players) == 2


async def test_v6_rules_round_trip_with_auto_register_false(
    session: AsyncSession,
) -> None:
    """A league created with `auto_register_players_on_match=False` round-trips
    through the JSONB column and reloads as `LeagueRules.auto_register_players_on_match=False`."""
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.rules = LeagueRules.from_dict(
        {
            "version": 6,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": False,
        }
    )
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    assert reloaded.rules.auto_register_players_on_match is False


async def test_match_count_surfaced_on_player_after_match(
    session: AsyncSession,
) -> None:
    """Players who have participated in a match must reload with
    `match_count >= 1` so `remove_player` can block deletion."""
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.register_players_and_team("alice", "bob")
    league.register_players_and_team("carol", "dave")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id_with_lock(league.league_id)
    t1 = next(
        t
        for t in reloaded.teams
        if {
            next(p.nickname.value for p in reloaded.players if p.player_id == t.player_id_1),
            next(p.nickname.value for p in reloaded.players if p.player_id == t.player_id_2),
        }
        == {"alice", "bob"}
    )
    t2 = next(
        t
        for t in reloaded.teams
        if {
            next(p.nickname.value for p in reloaded.players if p.player_id == t.player_id_1),
            next(p.nickname.value for p in reloaded.players if p.player_id == t.player_id_2),
        }
        == {"carol", "dave"}
    )

    import uuid

    from app.infrastructure.persistence.models.orm_models import MatchORM

    match_orm = MatchORM(
        match_id=uuid.uuid4(),
        league_id=reloaded.league_id.value,
        team1_id=t1.team_id.value,
        team2_id=t2.team_id.value,
        team1_score="6",
        team2_score="4",
    )
    session.add(match_orm)
    await repo.save(reloaded)
    await session.commit()
    session.expire_all()

    final = await repo.get_by_id(league.league_id)
    participants = {
        p.nickname.value for p in final.players if p.match_count > 0
    }
    assert participants == {"alice", "bob", "carol", "dave"}
    for p in final.players:
        assert p.match_count == 1


async def test_match_count_zero_for_roster_only_players(
    session: AsyncSession,
) -> None:
    """Players added via `add_players` but never on a team load with
    `match_count == 0`."""
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league()
    league.add_players(["alex", "daniel"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    for p in reloaded.players:
        assert p.match_count == 0
