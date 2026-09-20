import asyncio
from functools import partial
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.application.use_cases.upload_planned_matches_use_case import UploadPlannedMatchesCommand, UploadPlannedMatchesUseCase
from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.infrastructure.persistence.models.orm_models import PlannedMatchORM
from app.infrastructure.persistence.repositories.league_repository import SqlAlchemyLeagueRepository
from app.infrastructure.persistence.repositories.planned_match_repository import SqlAlchemyPlannedMatchRepository
from app.infrastructure.persistence.unit_of_work.upload_planned_matches_uow import SqlAlchemyUploadPlannedMatchesUnitOfWork


async def test_upsert_round_trip_order_and_league_isolation(session, persisted_league):
    other = League.create("Other plans", None, "token", "host@example.com")
    await SqlAlchemyLeagueRepository(session).save(other)
    repo = SqlAlchemyPlannedMatchRepository(session)
    league_id = persisted_league.league_id
    first, second, third = (UUID(int=i) for i in (1, 2, 3))
    original = [PlannedMatch.create(league_id, second, "민수 지수"), PlannedMatch.create(league_id, first, "Alice,Bob Charlie,Diana")]
    await repo.upsert_many(original)
    await repo.upsert_many(original)
    await repo.upsert_many([PlannedMatch.create(league_id, first, "Updated Name"), PlannedMatch.create(league_id, third, "A A")])
    await repo.upsert_many([PlannedMatch.create(other.league_id, first, "Other League")])
    await session.commit()
    assert [(m.id, m.value.value) for m in await repo.get_all_by_league(league_id)] == [
        (first, "Updated Name"), (second, "민수 지수"), (third, "A A"),
    ]
    assert [(m.id, m.value.value) for m in await repo.get_all_by_league(other.league_id)] == [(first, "Other League")]
    assert await SqlAlchemyLeagueRepository(session).exists(league_id)
    assert not await SqlAlchemyLeagueRepository(session).exists(LeagueId.generate())


async def test_primary_key_foreign_key_and_cascade(session, persisted_league):
    league_id, id = persisted_league.league_id, uuid4()
    repo = SqlAlchemyPlannedMatchRepository(session)
    await repo.upsert_many([PlannedMatch.create(league_id, id, "A B")])
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            session.add(PlannedMatchORM(league_id=league_id.value, id=id, value="C D"))
            await session.flush()
    with pytest.raises(IntegrityError):
        async with session.begin_nested():
            await repo.upsert_many([PlannedMatch.create(LeagueId.generate(), id, "C D")])
    await session.execute(text("DELETE FROM leagues WHERE league_id = :id"), {"id": league_id.value})
    assert await repo.get_all_by_league(league_id) == []


@pytest.mark.parametrize("failure_at", ["storage", "commit"])
async def test_failure_rolls_back_inserts_and_updates(session_factory, persisted_league, monkeypatch, failure_at):
    league_id, existing_id, new_id = persisted_league.league_id, uuid4(), uuid4()
    use_case = UploadPlannedMatchesUseCase(partial(SqlAlchemyUploadPlannedMatchesUnitOfWork, session_factory))
    await use_case.execute(UploadPlannedMatchesCommand(str(league_id), [PlannedMatchRecord(existing_id, "Original Value")]))
    if failure_at == "storage":
        original = SqlAlchemyPlannedMatchRepository.upsert_many

        async def fail_after_writes(self, matches):
            await original(self, matches)
            await self._session.execute(text("SELECT 1 / 0"))

        monkeypatch.setattr(SqlAlchemyPlannedMatchRepository, "upsert_many", fail_after_writes)
        error = DBAPIError
    else:
        async def fail_commit(self):
            raise RuntimeError("commit failed")

        monkeypatch.setattr(SqlAlchemyUploadPlannedMatchesUnitOfWork, "commit", fail_commit)
        error = RuntimeError
    with pytest.raises(error):
        await use_case.execute(UploadPlannedMatchesCommand(str(league_id), [
            PlannedMatchRecord(existing_id, "Changed Value"), PlannedMatchRecord(new_id, "New Value"),
        ]))
    async with session_factory() as fresh_session:
        plans = await SqlAlchemyPlannedMatchRepository(fresh_session).get_all_by_league(league_id)
        assert [(m.id, m.value.value) for m in plans] == [(existing_id, "Original Value")]


async def test_concurrent_upserts_do_not_create_duplicates(session_factory, persisted_league):
    id = uuid4()
    use_case = UploadPlannedMatchesUseCase(partial(SqlAlchemyUploadPlannedMatchesUnitOfWork, session_factory))
    values = ["Alice Bob", "민수 지수"]
    await asyncio.gather(*[
        use_case.execute(UploadPlannedMatchesCommand(str(persisted_league.league_id), [PlannedMatchRecord(id, value)]))
        for value in values
    ])
    async with session_factory() as session:
        plans = await SqlAlchemyPlannedMatchRepository(session).get_all_by_league(persisted_league.league_id)
        assert len(plans) == 1
        assert plans[0].id == id
        assert plans[0].value.value in values


async def test_locked_lookup_and_delete_are_scoped_and_transactional(session_factory, persisted_league):
    from app.domain.exceptions import PlannedMatchNotFoundError

    league_id, plan_id = persisted_league.league_id, uuid4()
    other = League.create("Other deletion league", None, "token", "host@example.com")
    async with session_factory() as session:
        await SqlAlchemyLeagueRepository(session).save(other)
        await session.flush()
        repo = SqlAlchemyPlannedMatchRepository(session)
        await repo.upsert_many([
            PlannedMatch.create(league_id, plan_id, "Alice Bob"),
            PlannedMatch.create(other.league_id, plan_id, "Other League"),
        ])
        await session.commit()
    async with session_factory() as session:
        repo = SqlAlchemyPlannedMatchRepository(session)
        assert (await repo.get_by_id_with_lock(league_id, plan_id)).value.value == "Alice Bob"
        assert await repo.get_by_id_with_lock(LeagueId.generate(), plan_id) is None
        with pytest.raises(PlannedMatchNotFoundError):
            await repo.delete(LeagueId.generate(), plan_id)
        await repo.delete(league_id, plan_id)
        assert await repo.get_by_id_with_lock(league_id, plan_id) is None
        assert (await repo.get_by_id_with_lock(other.league_id, plan_id)).value.value == "Other League"
        await session.rollback()
    async with session_factory() as session:
        repo = SqlAlchemyPlannedMatchRepository(session)
        assert await repo.get_by_id_with_lock(league_id, plan_id) is not None
        await repo.delete(league_id, plan_id)
        await session.commit()
    async with session_factory() as session:
        repo = SqlAlchemyPlannedMatchRepository(session)
        assert await repo.get_by_id_with_lock(league_id, plan_id) is None
        assert await repo.get_by_id_with_lock(other.league_id, plan_id) is not None


async def test_lightweight_league_lock_does_not_load_roster(session, persisted_league, monkeypatch):
    from unittest.mock import AsyncMock

    repo = SqlAlchemyLeagueRepository(session)
    load_counts = AsyncMock(side_effect=AssertionError("roster hydration is not allowed"))
    monkeypatch.setattr(repo, "_load_match_counts_by_player", load_counts)
    assert await repo.lock_by_id(persisted_league.league_id)
    assert not await repo.lock_by_id(LeagueId.generate())
    assert not session.identity_map
    load_counts.assert_not_called()
