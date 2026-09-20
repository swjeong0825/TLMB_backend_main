"""Atomic planned consumption through the existing result endpoints, on PostgreSQL."""
import asyncio
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.dependencies import AsyncSessionFactory
from app.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from app.infrastructure.persistence.repositories.planned_match_repository import SqlAlchemyPlannedMatchRepository
from app.infrastructure.persistence.repositories.singles_match_repository import SqlAlchemySinglesMatchRepository
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import SqlAlchemySubmitMatchResultUnitOfWork
from app.infrastructure.persistence.unit_of_work.submit_singles_match_result_uow import SqlAlchemySubmitSinglesMatchResultUnitOfWork
from app.main import app


@pytest.fixture(params=["singles", "doubles"])
def recording(request):
    if request.param == "singles":
        return {
            "format": "singles", "endpoint": "singles-matches", "value": "Alice Bob",
            "payload": {"player1_nickname": "Alice", "player2_nickname": "Bob", "player1_score": "6", "player2_score": "0"},
            "score": "player1_score", "repo": SqlAlchemySinglesMatchRepository,
            "uow": SqlAlchemySubmitSinglesMatchResultUnitOfWork,
        }
    return {
        "format": "doubles", "endpoint": "matches", "value": "Alice,Bob Charlie,Diana",
        "payload": {"pair1_nicknames": ["Alice", "Bob"], "pair2_nicknames": ["Charlie", "Diana"], "pair1_score": "6", "pair2_score": "0"},
        "score": "pair1_score", "repo": SqlAlchemyMatchRepository,
        "uow": SqlAlchemySubmitMatchResultUnitOfWork,
    }


async def create_league(client, **rules):
    response = await client.post("/leagues", json={
        "title": str(uuid4()), "host_email": "host@example.com",
        "rules": {"version": 8, "pair_matchup_idempotency": "none", **rules},
    })
    assert response.status_code == 201, response.text
    return response.json()


async def upload(client, league_id, value, plan_id=None):
    record = {"id": str(plan_id or uuid4()), "value": value}
    response = await client.post(f"/leagues/{league_id}/planned-matches", json={"matches": [record]})
    assert response.status_code == 200, response.text
    return record


async def setup(client, recording, **rules):
    league = await create_league(client, **rules)
    lid = league["league_id"]
    plan = await upload(client, lid, recording["value"])
    return league, plan, f"/leagues/{lid}/{recording['endpoint']}", {**recording["payload"], "planned_match_id": plan["id"]}


async def snapshot(client, league_id):
    async with AsyncSessionFactory() as session:
        state = {}
        for table in ("leagues", "players", "player_aliases", "pairs", "matches", "singles_matches", "planned_matches"):
            rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
            state[table] = sorted(rows.scalars().all())
    state["standings"] = (await client.get(f"/leagues/{league_id}/standings?scope=both")).json()
    return state


async def test_consumes_plan_records_history_and_standings_and_retry_is_404(client, recording):
    league, plan, url, payload = await setup(client, recording)
    if recording["format"] == "doubles":
        payload["pair1_nicknames"] = [" BOB\ufeff", "ALICE"]
    else:
        payload["player1_nickname"] = " ALICE\ufeff"
    response = await client.post(url, json=payload)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"match_id", "created_at"}
    lid = league["league_id"]
    assert (await client.get(f"/leagues/{lid}/planned-matches")).json() == {"matches": []}
    history = (await client.get(f"/leagues/{lid}/matches?scope=both")).json()["matches"]
    assert len(history) == 1
    assert history[0]["match_id"] == response.json()["match_id"]
    assert history[0]["created_at"] == response.json()["created_at"]
    assert history[0]["match_format"] == recording["format"]
    assert history[0][recording["score"]] == "6"
    assert history[0][recording["score"].replace("1", "2")] == "0"
    standings = (await client.get(f"/leagues/{lid}/standings?scope={recording['format']}")).json()["standings"]
    assert sum(row["wins"] for row in standings) == 1
    roster = (await client.get(f"/leagues/{lid}/roster")).json()
    assert roster["latest_activity_date"] is not None
    before_retry = await snapshot(client, lid)
    retry = await client.post(url, json=payload)
    assert retry.status_code == 404
    assert retry.json()["error"] == "PlannedMatchNotFoundError"
    assert await snapshot(client, lid) == before_retry
    # There is intentionally no consumed-ID ledger: upload can recreate this UUID.
    await upload(client, lid, plan["value"], plan["id"])
    assert (await client.get(f"/leagues/{lid}/planned-matches")).json() == {"matches": [plan]}


@pytest.mark.parametrize("include_null", [False, True])
async def test_manual_recording_leaves_existing_plan_pending(client, recording, include_null):
    league, plan, url, payload = await setup(client, recording)
    payload.pop("planned_match_id")
    if include_null:
        payload["planned_match_id"] = None
    response = await client.post(url, json=payload)
    assert response.status_code == 201, response.text
    assert (await client.get(f"/leagues/{league['league_id']}/planned-matches")).json() == {"matches": [plan]}


@pytest.mark.parametrize("failure", ["missing", "format", "names", "swapped", "score", "closed_roster", "repeated"])
async def test_rejected_recording_keeps_all_state(client, recording, failure):
    league, plan, url, payload = await setup(client, recording, auto_register_players_on_match=failure != "closed_roster")
    lid = league["league_id"]
    expected_status = 422
    if failure == "missing":
        payload["planned_match_id"] = str(uuid4())
        expected_status = 404
    elif failure == "format":
        await upload(client, lid, "Alice,Bob Charlie,Diana" if recording["format"] == "singles" else "Alice Bob", plan["id"])
    elif failure in ("names", "swapped"):
        first, second = ("player1_nickname", "player2_nickname") if recording["format"] == "singles" else ("pair1_nicknames", "pair2_nicknames")
        if failure == "swapped":
            payload[first], payload[second] = payload[second], payload[first]
        else:
            payload[first] = "Other" if recording["format"] == "singles" else ["Other", "Bob"]
        expected_status = 409
    elif failure == "score":
        payload[recording["score"]] = "-1"
    elif failure == "repeated":
        if recording["format"] == "singles":
            value = "Alice Alice"
            payload["player2_nickname"] = "Alice"
        else:
            value = "Alice,Alice Charlie,Diana"
            payload["pair1_nicknames"] = ["Alice", "Alice"]
        await upload(client, lid, value, plan["id"])
    before = await snapshot(client, lid)
    response = await client.post(url, json=payload)
    assert response.status_code == expected_status, response.text
    assert await snapshot(client, lid) == before


async def test_plan_ids_are_scoped_to_league(client, recording):
    league, plan, url, payload = await setup(client, recording)
    other = await create_league(client)
    other_url = f"/leagues/{other['league_id']}/{recording['endpoint']}"
    assert (await client.post(other_url, json=payload)).status_code == 404
    assert (await client.post(f"/leagues/{uuid4()}/{recording['endpoint']}", json=payload)).status_code == 404
    await upload(client, other["league_id"], plan["value"], plan["id"])
    assert (await client.post(url, json=payload)).status_code == 201
    assert (await client.get(f"/leagues/{other['league_id']}/planned-matches")).json() == {"matches": [plan]}
    assert (await client.post(other_url, json=payload)).status_code == 201


@pytest.mark.parametrize("policy", ["none", "once_per_league", "once_per_day"])
async def test_rematch_rules_still_apply(client, recording, policy):
    league, _, url, payload = await setup(client, recording, pair_matchup_idempotency=policy)
    assert (await client.post(url, json=recording["payload"])).status_code == 201
    before = await snapshot(client, league["league_id"])
    response = await client.post(url, json=payload)
    assert response.status_code == (201 if policy == "none" else 409), response.text
    if policy != "none":
        assert await snapshot(client, league["league_id"]) == before


async def test_alias_names_must_match_plan_before_normal_resolution(client, recording):
    league, plan, url, payload = await setup(client, recording)
    lid = league["league_id"]
    assert (await client.post(url, json=recording["payload"])).status_code == 201
    players = (await client.get(f"/leagues/{lid}/roster")).json()["players"]
    alice = next(player for player in players if player["nickname"] == "alice")
    alias = await client.post(f"/admin/leagues/{lid}/players/{alice['player_id']}/aliases", json={"alias": "Ace"}, headers={"X-Host-Token": league["host_token"]})
    assert alias.status_code == 201, alias.text
    await upload(client, lid, plan["value"].replace("Alice", "Ace"), plan["id"])
    before = await snapshot(client, lid)
    assert (await client.post(url, json=payload)).status_code == 409
    assert await snapshot(client, lid) == before
    if recording["format"] == "singles":
        payload["player1_nickname"] = "ACE"
    else:
        payload["pair1_nicknames"] = ["ACE", "Bob"]
    assert (await client.post(url, json=payload)).status_code == 201
    after = (await client.get(f"/leagues/{lid}/roster")).json()["players"]
    assert len(after) == len(players)


@pytest.mark.parametrize("failure_at", ["result_insert", "plan_delete", "commit"])
async def test_storage_failure_restores_plan_and_every_result_side_effect(client, recording, monkeypatch, failure_at):
    league, _, url, payload = await setup(client, recording)
    lid = league["league_id"]
    before = await snapshot(client, lid)
    target, method = {
        "result_insert": (recording["repo"], "save"),
        "plan_delete": (SqlAlchemyPlannedMatchRepository, "delete"),
        "commit": (recording["uow"], "commit"),
    }[failure_at]
    original = getattr(target, method)

    async def fail_after_writes(self, *args):
        if failure_at == "commit":
            await self._session.flush()
        else:
            await original(self, *args)
        await self._session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(target, method, fail_after_writes)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as error_client:
        response = await error_client.post(url, json=payload)
    assert response.status_code == 500
    assert await snapshot(client, lid) == before


@pytest.mark.parametrize("same_score", [True, False])
async def test_concurrent_recordings_create_only_one_result(client, recording, same_score):
    league, _, url, payload = await setup(client, recording)
    second = {**payload, recording["score"]: "6" if same_score else "3"}
    responses = await asyncio.wait_for(asyncio.gather(client.post(url, json=payload), client.post(url, json=second)), timeout=10)
    assert sorted(response.status_code for response in responses) == [201, 404]
    lid = league["league_id"]
    history = (await client.get(f"/leagues/{lid}/matches?scope=both")).json()["matches"]
    assert len(history) == 1
    assert (await client.get(f"/leagues/{lid}/planned-matches")).json() == {"matches": []}


@pytest.mark.parametrize("record_first", [True, False])
async def test_upload_and_record_use_the_same_league_lock(client, recording, monkeypatch, record_first):
    from app.infrastructure.persistence.repositories.league_repository import SqlAlchemyLeagueRepository

    league, plan, url, payload = await setup(client, recording)
    lid = league["league_id"]
    changed = "Eve Frank" if recording["format"] == "singles" else "Eve,Frank Grace,Heidi"
    first_locked, second_started, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    blocked_pids = []
    pause_method = "get_by_id_with_lock" if record_first else "upsert_many"
    real_first = getattr(SqlAlchemyPlannedMatchRepository, pause_method)

    async def pause_first(self, *args):
        result = await real_first(self, *args)
        first_locked.set()
        await release.wait()
        return result

    second_method = "lock_by_id" if record_first else "get_by_id_with_lock"
    real_second_lock = getattr(SqlAlchemyLeagueRepository, second_method)

    async def observe_second_lock(self, *args):
        blocked_pids.append(await self._session.scalar(text("SELECT pg_backend_pid()")))
        second_started.set()
        return await real_second_lock(self, *args)

    monkeypatch.setattr(SqlAlchemyPlannedMatchRepository, pause_method, pause_first)
    monkeypatch.setattr(SqlAlchemyLeagueRepository, second_method, observe_second_lock)
    operations = [
        lambda: client.post(url, json=payload),
        lambda: client.post(f"/leagues/{lid}/planned-matches", json={"matches": [{"id": plan["id"], "value": changed}]}),
    ]
    if not record_first:
        operations.reverse()
    tasks = [asyncio.create_task(operations[0]())]
    try:
        await asyncio.wait_for(first_locked.wait(), 5)
        tasks.append(asyncio.create_task(operations[1]()))
        await asyncio.wait_for(second_started.wait(), 5)
        # Observe an actual PostgreSQL lock wait, rather than relying on timing.
        async with AsyncSessionFactory() as observer:
            async with asyncio.timeout(5):
                while not await observer.scalar(text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": blocked_pids[0]}):
                    await asyncio.sleep(0.01)
        assert not tasks[1].done()
    finally:
        release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 10)
    assert [response.status_code for response in responses] == ([201, 200] if record_first else [200, 409])
    assert (await client.get(f"/leagues/{lid}/planned-matches")).json() == {"matches": [{"id": plan["id"], "value": changed}]}
    history = (await client.get(f"/leagues/{lid}/matches?scope=both")).json()["matches"]
    assert len(history) == (1 if record_first else 0)


@pytest.mark.parametrize("one_pair", [True, False])
async def test_planned_doubles_obey_pair_membership_rule(client, one_pair):
    league = await create_league(client, one_pair_per_player=one_pair)
    lid = league["league_id"]
    url = f"/leagues/{lid}/matches"
    payload = {"pair1_nicknames": ["Alice", "Bob"], "pair2_nicknames": ["Charlie", "Diana"], "pair1_score": "6", "pair2_score": "0"}
    assert (await client.post(url, json=payload)).status_code == 201
    plan = await upload(client, lid, "Alice,Charlie Bob,Diana")
    payload.update(pair1_nicknames=["Alice", "Charlie"], pair2_nicknames=["Bob", "Diana"], planned_match_id=plan["id"])
    before = await snapshot(client, lid)
    response = await client.post(url, json=payload)
    assert response.status_code == (409 if one_pair else 201), response.text
    if one_pair:
        assert response.json()["error"] == "PairConflictError"
        assert await snapshot(client, lid) == before
