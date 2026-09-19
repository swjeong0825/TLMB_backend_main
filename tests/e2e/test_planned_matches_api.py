from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.dependencies import AsyncSessionFactory
from app.infrastructure.persistence.repositories.planned_match_repository import SqlAlchemyPlannedMatchRepository
from app.main import app


async def create_league(client, **overrides):
    response = await client.post("/leagues", json={"title": str(uuid4()), "host_email": "host@example.com", **overrides})
    assert response.status_code == 201, response.text
    return response.json()


def record(value="Alice Bob", id=None):
    return {"id": str(id or uuid4()), "value": value}


async def test_round_trips_retry_update_append_order_and_isolation(client):
    league, other = await create_league(client), await create_league(client)
    url = f"/leagues/{league['league_id']}/planned-matches"
    other_url = f"/leagues/{other['league_id']}/planned-matches"
    assert (await client.get(url)).json() == {"matches": []}
    records = [record("민수 지수", UUID(int=2)), record("Alice,Bob Charlie,Diana", UUID(int=1))]
    for _ in range(2):
        response = await client.post(url, json={"matches": records})
        assert response.status_code == 200, response.text
        assert response.json() == {"matches": records}
    assert (await client.get(url)).json() == {"matches": list(reversed(records))}
    changed = record("Unknown UNKNOWN", UUID(int=2))
    added = record("A,A A,A", UUID(int=3))
    assert (await client.post(url, json={"matches": [changed, added]})).status_code == 200
    assert (await client.get(url)).json() == {"matches": [records[1], changed, added]}
    other_record = record("Other League", UUID(int=2))
    assert (await client.post(other_url, json={"matches": [other_record]})).status_code == 200
    assert (await client.get(other_url)).json() == {"matches": [other_record]}
    assert (await client.get(url)).json() == {"matches": [records[1], changed, added]}


async def test_mixed_invalid_batch_leaves_inserts_and_updates_untouched(client):
    league = await create_league(client)
    url = f"/leagues/{league['league_id']}/planned-matches"
    original = record("Original Value")
    await client.post(url, json={"matches": [original]})
    response = await client.post(url, json={"matches": [record("Changed Value", original["id"]), record(), record("bad")]})
    assert response.status_code == 422
    assert (await client.get(url)).json() == {"matches": [original]}


async def test_storage_failure_returns_5xx_without_partial_writes(client, monkeypatch):
    league = await create_league(client)
    url = f"/leagues/{league['league_id']}/planned-matches"
    original = record("Original Value")
    await client.post(url, json={"matches": [original]})
    real_upsert = SqlAlchemyPlannedMatchRepository.upsert_many

    async def fail_after_writes(self, matches):
        await real_upsert(self, matches)
        await self._session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(SqlAlchemyPlannedMatchRepository, "upsert_many", fail_after_writes)
    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as error_client:
        response = await error_client.post(url, json={"matches": [record("Changed Value", original["id"]), record()]})
    assert response.status_code == 500
    assert (await client.get(url)).json() == {"matches": [original]}


async def test_missing_leagues_return_404(client):
    url = f"/leagues/{uuid4()}/planned-matches"
    assert (await client.get(url)).status_code == 404
    assert (await client.post(url, json={"matches": [record()]})).status_code == 404


@pytest.mark.parametrize("auto_register", [True, False])
@pytest.mark.parametrize("one_pair", [True, False])
@pytest.mark.parametrize("rematches", ["none", "once_per_league", "once_per_day"])
async def test_upload_does_not_change_domain_state(client, auto_register, one_pair, rematches):
    league = await create_league(client, initial_players=["Alice", "Bob", "Charlie", "Diana"], rules={
        "version": 8, "auto_register_players_on_match": auto_register,
        "one_pair_per_player": one_pair, "pair_matchup_idempotency": rematches,
        "ranking_subject": "pair", "tie_breakers": ["matches_won"],
    })
    lid = league["league_id"]
    headers = {"X-Host-Token": league["host_token"]}
    roster = (await client.get(f"/leagues/{lid}/roster")).json()
    player_id = roster["players"][0]["player_id"]
    assert (await client.post(f"/admin/leagues/{lid}/players/{player_id}/aliases", headers=headers, json={"alias": "Ace"})).status_code == 201
    assert (await client.post(f"/leagues/{lid}/matches", json={
        "pair1_nicknames": ["Alice", "Bob"], "pair2_nicknames": ["Charlie", "Diana"], "pair1_score": "6", "pair2_score": "3",
    })).status_code == 201
    assert (await client.post(f"/leagues/{lid}/singles-matches", json={
        "player1_nickname": "Alice", "player2_nickname": "Bob", "player1_score": "6", "player2_score": "4",
    })).status_code == 201

    async def snapshot():
        async with AsyncSessionFactory() as session:
            state = {}
            for table in ("leagues", "players", "player_aliases", "pairs", "matches", "singles_matches"):
                rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
                state[table] = sorted(rows.scalars().all())
        state["standings"] = (await client.get(f"/leagues/{lid}/standings", params={"scope": "both"})).json()
        return state

    before = await snapshot()
    response = await client.post(f"/leagues/{lid}/planned-matches", json={"matches": [
        record("Unknown 미등록"), record("Alice,Charlie Bob,Diana"), record("Alice,Bob Charlie,Diana"), record("Ace,Ace Ace,Ace"),
    ]})
    assert response.status_code == 200, response.text
    assert await snapshot() == before
