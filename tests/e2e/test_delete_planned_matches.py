"""Delete pending plans through HTTP against isolated PostgreSQL."""
import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.dependencies import AsyncSessionFactory
from app.infrastructure.persistence.repositories.league_repository import SqlAlchemyLeagueRepository
from app.infrastructure.persistence.repositories.planned_match_repository import SqlAlchemyPlannedMatchRepository
from app.infrastructure.persistence.unit_of_work.delete_planned_match_uow import SqlAlchemyDeletePlannedMatchUnitOfWork
from app.main import app


async def create_league(client, auto_register=True):
    response = await client.post('/leagues', json={
        'title': str(uuid4()), 'host_email': 'host@example.com',
        'initial_players': ['Alice', 'Bob', 'Charlie', 'Diana'],
        'rules': {'version': 8, 'pair_matchup_idempotency': 'none', 'auto_register_players_on_match': auto_register},
    })
    assert response.status_code == 201, response.text
    return response.json()


async def upload(client, league_id, value='Alice Bob', plan_id=None):
    plan = {'id': str(plan_id or uuid4()), 'value': value}
    response = await client.post(f'/leagues/{league_id}/planned-matches', json={'matches': [plan]})
    assert response.status_code == 200, response.text
    return plan


async def snapshot(client, league_id):
    async with AsyncSessionFactory() as session:
        state = {}
        for table in ('leagues', 'players', 'player_aliases', 'pairs', 'matches', 'singles_matches', 'planned_matches'):
            rows = await session.execute(text(f'SELECT row_to_json(t)::text FROM {table} t'))
            state[table] = sorted(rows.scalars().all())
    state['standings'] = (await client.get(f'/leagues/{league_id}/standings?scope=both')).json()
    return state


@pytest.mark.parametrize('auto_register', [True, False])
@pytest.mark.parametrize('value', ['Alice Bob', 'Unknown,Unknown Unknown,Unknown'])
async def test_deletes_only_target_plan_without_domain_side_effects(client, auto_register, value):
    league = await create_league(client, auto_register)
    lid = league['league_id']
    assert (await client.post(f'/leagues/{lid}/matches', json={
        'pair1_nicknames': ['Alice', 'Bob'], 'pair2_nicknames': ['Charlie', 'Diana'],
        'pair1_score': '6', 'pair2_score': '3',
    })).status_code == 201
    assert (await client.post(f'/leagues/{lid}/singles-matches', json={
        'player1_nickname': 'Alice', 'player2_nickname': 'Bob', 'player1_score': '6', 'player2_score': '0',
    })).status_code == 201
    player = (await client.get(f'/leagues/{lid}/roster')).json()['players'][0]
    assert (await client.post(f"/admin/leagues/{lid}/players/{player['player_id']}/aliases", json={'alias': 'Ace'}, headers={'X-Host-Token': league['host_token']})).status_code == 201
    plan = await upload(client, lid, value)
    spare = await upload(client, lid, '민수 지수')
    other = await create_league(client)
    other_plan = await upload(client, other['league_id'], 'Other League', plan['id'])
    before = await snapshot(client, lid)
    url = f"/leagues/{lid}/planned-matches/{plan['id']}"
    response = await client.delete(url)
    assert response.status_code == 204, response.text
    assert response.content == b''
    assert (await client.get(f'/leagues/{lid}/planned-matches')).json() == {'matches': [spare]}
    assert (await client.get(f"/leagues/{other['league_id']}/planned-matches")).json() == {'matches': [other_plan]}
    after = await snapshot(client, lid)
    assert len(after.pop('planned_matches')) == len(before.pop('planned_matches')) - 1
    assert after == before
    retry = await client.delete(url)
    assert retry.status_code == 404
    assert retry.json()['error'] == 'PlannedMatchNotFoundError'
    # Deletion leaves no tombstone; a later upload may intentionally reuse the ID.
    await upload(client, lid, value, plan['id'])


async def test_missing_league_and_foreign_plan_return_404_without_changes(client):
    league, other = await create_league(client), await create_league(client)
    lid = league['league_id']
    plan = await upload(client, lid)
    before = await snapshot(client, lid)
    for target_league, plan_id, error in [
        (str(uuid4()), plan['id'], 'LeagueNotFoundError'),
        (other['league_id'], plan['id'], 'PlannedMatchNotFoundError'),
        (lid, str(uuid4()), 'PlannedMatchNotFoundError'),
    ]:
        response = await client.delete(f'/leagues/{target_league}/planned-matches/{plan_id}')
        assert response.status_code == 404
        assert response.json()['error'] == error
    assert await snapshot(client, lid) == before


async def test_delete_by_id_can_remove_a_malformed_saved_value(client):
    league = await create_league(client)
    lid = league['league_id']
    plan = await upload(client, lid)
    async with AsyncSessionFactory() as session:
        await session.execute(text('UPDATE planned_matches SET value = :value WHERE league_id = :lid AND id = :id'), {'value': 'malformed', 'lid': lid, 'id': plan['id']})
        await session.commit()
    assert (await client.delete(f"/leagues/{lid}/planned-matches/{plan['id']}")).status_code == 204
    assert (await client.get(f'/leagues/{lid}/planned-matches')).json() == {'matches': []}


@pytest.mark.parametrize('failure_at', ['delete', 'commit'])
async def test_failure_restores_deleted_plan(client, monkeypatch, failure_at):
    league = await create_league(client)
    lid = league['league_id']
    plan = await upload(client, lid)
    before = await snapshot(client, lid)
    target = SqlAlchemyPlannedMatchRepository if failure_at == 'delete' else SqlAlchemyDeletePlannedMatchUnitOfWork
    original = getattr(target, failure_at)

    async def fail(self, *args):
        if failure_at == 'delete':
            await original(self, *args)
            await self._session.execute(text('SELECT 1 / 0'))
        else:
            raise RuntimeError('commit failed')

    monkeypatch.setattr(target, failure_at, fail)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test') as error_client:
        response = await error_client.delete(f"/leagues/{lid}/planned-matches/{plan['id']}")
    assert response.status_code == 500
    assert await snapshot(client, lid) == before


async def test_concurrent_deletes_have_one_success(client):
    league = await create_league(client)
    lid = league['league_id']
    plan = await upload(client, lid)
    url = f"/leagues/{lid}/planned-matches/{plan['id']}"
    responses = await asyncio.wait_for(asyncio.gather(client.delete(url), client.delete(url)), 10)
    assert sorted(response.status_code for response in responses) == [204, 404]
    assert (await client.get(f'/leagues/{lid}/planned-matches')).json() == {'matches': []}


@pytest.mark.parametrize('match_format', ['singles', 'doubles'])
@pytest.mark.parametrize('delete_first', [True, False])
async def test_delete_and_record_serialize_on_the_league(client, monkeypatch, match_format, delete_first):
    league = await create_league(client)
    lid = league['league_id']
    value = 'Alice Bob' if match_format == 'singles' else 'Alice,Bob Charlie,Diana'
    plan = await upload(client, lid, value)
    payload = {'planned_match_id': plan['id']}
    if match_format == 'singles':
        endpoint = 'singles-matches'
        payload.update(player1_nickname='Alice', player2_nickname='Bob', player1_score='6', player2_score='0')
    else:
        endpoint = 'matches'
        payload.update(pair1_nicknames=['Alice', 'Bob'], pair2_nicknames=['Charlie', 'Diana'], pair1_score='6', pair2_score='0')
    first_deleted, second_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_delete = SqlAlchemyPlannedMatchRepository.delete
    waiting_pids = []

    async def pause_first_delete(self, *args):
        await real_delete(self, *args)
        if not first_deleted.is_set():
            first_deleted.set()
            await release.wait()

    monkeypatch.setattr(SqlAlchemyPlannedMatchRepository, 'delete', pause_first_delete)
    operations = [
        lambda: client.delete(f"/leagues/{lid}/planned-matches/{plan['id']}"),
        lambda: client.post(f'/leagues/{lid}/{endpoint}', json=payload),
    ]
    if not delete_first:
        operations.reverse()
    tasks = [asyncio.create_task(operations[0]())]
    try:
        await asyncio.wait_for(first_deleted.wait(), 5)
        lock_method = 'get_by_id_with_lock' if delete_first else 'lock_by_id'
        real_lock = getattr(SqlAlchemyLeagueRepository, lock_method)

        async def observe_second_lock(self, *args):
            waiting_pids.append(await self._session.scalar(text('SELECT pg_backend_pid()')))
            second_started.set()
            return await real_lock(self, *args)

        monkeypatch.setattr(SqlAlchemyLeagueRepository, lock_method, observe_second_lock)
        tasks.append(asyncio.create_task(operations[1]()))
        await asyncio.wait_for(second_started.wait(), 5)
        async with AsyncSessionFactory() as observer:
            async with asyncio.timeout(5):
                while not await observer.scalar(text('SELECT cardinality(pg_blocking_pids(:pid)) > 0'), {'pid': waiting_pids[0]}):
                    await asyncio.sleep(0.01)
        assert not tasks[1].done()
    finally:
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
    assert [response.status_code for response in responses] == ([204, 404] if delete_first else [201, 404])
    assert (await client.get(f'/leagues/{lid}/planned-matches')).json() == {'matches': []}
    history = (await client.get(f'/leagues/{lid}/matches?scope=both')).json()['matches']
    assert len(history) == (0 if delete_first else 1)
