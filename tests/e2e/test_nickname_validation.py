from urllib.parse import quote
from uuid import UUID

import pytest
from sqlalchemy import text

from app.dependencies import AsyncSessionFactory


@pytest.mark.parametrize("path", ["initial", "add", "rated", "rename", "alias", "singles", "doubles"])
@pytest.mark.parametrize("name,valid", [
    ("Alice", True), ("민수", True), ("A-1", True), ("B_2", True), ("C.3", True),
    ("  Alice  ", True), ("\ufeffAlice\ufeff", True),
    ("", False), (" \t ", False), ("Alice Smith", False), ("Alice,Bob", False),
    ("Alice\tBob", False), ("Alice\nBob", False), ("Alice\u00a0Bob", False),
])
async def test_nickname_rule_on_every_write_path(client, path, name, valid):
    created = await client.post("/leagues", json={
        "title": "Nickname paths", "host_email": "host@example.com", "initial_players": ["existing"],
    })
    assert created.status_code == 201, created.text
    league = created.json()
    lid = league["league_id"]
    headers = {"X-Host-Token": league["host_token"]}
    roster_url = f"/leagues/{lid}/roster"
    before = (await client.get(roster_url)).json()
    pid = before["players"][0]["player_id"]
    admin = f"/admin/leagues/{lid}/players"
    if path == "initial":
        response = await client.post("/leagues", json={
            "title": "Input league", "host_email": "host@example.com", "initial_players": ["valid", name],
        })
        if valid:
            roster_url = f"/leagues/{response.json()['league_id']}/roster"
    elif path == "add":
        response = await client.post(admin, headers=headers, json={"nicknames": ["valid", name]})
    elif path == "rated":
        response = await client.post(admin, headers=headers, json={"players": [{"nickname": "valid"}, {"nickname": name, "rating": 3.5}]})
    elif path == "rename":
        response = await client.patch(f"{admin}/{pid}", headers=headers, json={"new_nickname": name})
    elif path == "alias":
        response = await client.post(f"{admin}/{pid}/aliases", headers=headers, json={"alias": name})
    elif path == "singles":
        response = await client.post(f"/leagues/{lid}/singles-matches", json={
            "player1_nickname": name, "player2_nickname": "opponent", "player1_score": "6", "player2_score": "3",
        })
    else:
        response = await client.post(f"/leagues/{lid}/matches", json={
            "pair1_nicknames": ["valid-b", name], "pair2_nicknames": ["valid-c", "valid-d"], "pair1_score": "6", "pair2_score": "3",
        })
    if valid:
        assert response.status_code == (200 if path == "rename" else 201), response.text
        roster = (await client.get(roster_url)).json()
        names = {nickname for player in roster["players"] for nickname in [player["nickname"], *player["aliases"]]}
        assert name.strip(" \ufeff").lower() in names
    else:
        assert response.status_code == 422, response.text
        assert (await client.get(roster_url)).json() == before
        async with AsyncSessionFactory() as session:
            assert await session.scalar(text("SELECT count(*) FROM leagues")) == 1


async def test_legacy_names_remain_readable_removable_and_correctable(client):
    response = await client.post("/leagues", json={
        "title": "Legacy", "host_email": "host@example.com",
        "initial_players": ["alice", "bob", "charlie", "diana", "removable"],
    })
    league = response.json()
    lid = league["league_id"]
    headers = {"X-Host-Token": league["host_token"]}
    roster = (await client.get(f"/leagues/{lid}/roster")).json()
    ids = {p["nickname"]: p["player_id"] for p in roster["players"]}
    assert (await client.post(f"/leagues/{lid}/matches", json={
        "pair1_nicknames": ["alice", "bob"], "pair2_nicknames": ["charlie", "diana"], "pair1_score": "6", "pair2_score": "3",
    })).status_code == 201
    # Simulate real pre-validation records, bypassing all new-write validators.
    async with AsyncSessionFactory() as session:
        await session.execute(text("UPDATE player_aliases SET alias_normalized = 'alice smith' WHERE alias_normalized = 'alice'"))
        await session.execute(text("UPDATE player_aliases SET alias_normalized = 'old,name' WHERE alias_normalized = 'removable'"))
        await session.execute(text(
            "INSERT INTO player_aliases (player_id, league_id, alias_normalized, is_canonical) VALUES (:pid, :lid, 'old alias', false)"
        ), {"pid": UUID(ids["alice"]), "lid": UUID(lid)})
        await session.commit()

    roster = (await client.get(f"/leagues/{lid}/roster")).json()
    alice = next(p for p in roster["players"] if p["player_id"] == ids["alice"])
    assert alice["nickname"] == "alice smith"
    assert alice["aliases"] == ["old alias"]
    for nickname in ("Alice Smith", "old alias"):
        response = await client.get(f"/leagues/{lid}/matches/by-player", params={"player_name": nickname})
        assert response.status_code == 200, response.text
        assert len(response.json()["matches"]) == 1
        response = await client.get(f"/leagues/{lid}/standings/by-player", params={"player_name": nickname})
        assert response.status_code == 200, response.text
        assert response.json()["standings"]

    # Rating-only edits must not revalidate or silently rewrite legacy names.
    player_url = f"/admin/leagues/{lid}/players/{ids['alice']}"
    assert (await client.patch(player_url, headers=headers, json={"rating": 3.5})).status_code == 200
    async with AsyncSessionFactory() as session:
        stored = (await session.execute(text("SELECT alias_normalized FROM player_aliases WHERE player_id = :pid"), {"pid": UUID(ids["alice"])})).scalars().all()
        assert set(stored) == {"alice smith", "old alias"}
    assert (await client.delete(f"{player_url}/aliases/{quote('old alias', safe='')}", headers=headers)).status_code == 204
    corrected = await client.patch(player_url, headers=headers, json={"new_nickname": "Alice"})
    assert corrected.status_code == 200
    assert corrected.json()["new_nickname"] == "alice"
    assert (await client.delete(f"/admin/leagues/{lid}/players/{ids['removable']}", headers=headers)).status_code == 204
    # Participation restrictions still apply to the corrected player.
    assert (await client.delete(player_url, headers=headers)).status_code == 409


async def test_lookup_prefers_exact_names_across_whitespace_conventions(client):
    response = await client.post("/leagues", json={
        "title": "Whitespace lookup", "host_email": "host@example.com",
        "initial_players": ["alice", "\u0085alice\u0085"],
    })
    assert response.status_code == 201
    lid = response.json()["league_id"]
    # U+0085 is not ECMAScript whitespace; these are two different legal names.
    response = await client.get(f"/leagues/{lid}/standings/by-player", params={
        "player_name": "\u0085alice\u0085", "scope": "singles",
    })
    assert response.status_code == 200, response.text
    assert response.json()["standings"][0]["nickname"] == "\u0085alice\u0085"
