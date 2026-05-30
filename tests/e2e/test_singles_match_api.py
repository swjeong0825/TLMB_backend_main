"""E2E tests for singles match submission and lifecycle APIs."""
from __future__ import annotations

from httpx import AsyncClient


_DEFAULT_HOST_EMAIL = "glhf0825@gmail.com"


async def create_league(client: AsyncClient, title: str = "Singles E2E League") -> dict:
    resp = await client.post(
        "/leagues",
        json={"title": title, "host_email": _DEFAULT_HOST_EMAIL},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def submit_singles_match(
    client: AsyncClient,
    league_id: str,
    player1: str = "alice",
    player2: str = "bob",
    player1_score: str = "6",
    player2_score: str = "3",
) -> dict:
    resp = await client.post(
        f"/leagues/{league_id}/singles-matches",
        json={
            "player1_nickname": player1,
            "player2_nickname": player2,
            "player1_score": player1_score,
            "player2_score": player2_score,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_submit_singles_match_success_and_roster_dates(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    result = await submit_singles_match(client, league_id)

    assert result["match_id"]
    assert result["created_at"]
    roster_resp = await client.get(f"/leagues/{league_id}/roster")
    assert roster_resp.status_code == 200, roster_resp.text
    roster = roster_resp.json()
    assert [p["nickname"] for p in roster["players"]] == ["alice", "bob"]
    assert roster["pairs"] == []
    assert roster["latest_match_date"] is None
    assert roster["latest_match_date_single"] is not None
    assert roster["latest_activity_date"] == roster["latest_match_date_single"]


async def test_submit_singles_same_player_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)

    resp = await client.post(
        f"/leagues/{league['league_id']}/singles-matches",
        json={
            "player1_nickname": "alice",
            "player2_nickname": " ALICE ",
            "player1_score": "6",
            "player2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "SamePlayerOnBothSidesError"


async def test_singles_standings_and_history_scopes(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]
    match = await submit_singles_match(client, league_id)

    standings_resp = await client.get(f"/leagues/{league_id}/standings?scope=singles")
    assert standings_resp.status_code == 200, standings_resp.text
    standings = standings_resp.json()["standings"]
    assert standings[0]["subject_kind"] == "player"
    assert standings[0]["nickname"] == "alice"
    assert standings[0]["wins"] == 1
    assert standings[1]["nickname"] == "bob"
    assert standings[1]["losses"] == 1

    invalid_resp = await client.get(
        f"/leagues/{league_id}/standings?subject=pair&scope=singles"
    )
    assert invalid_resp.status_code == 422

    history_resp = await client.get(f"/leagues/{league_id}/matches?scope=both")
    assert history_resp.status_code == 200, history_resp.text
    row = history_resp.json()["matches"][0]
    assert row["match_id"] == match["match_id"]
    assert row["match_format"] == "singles"
    assert row["player1_nickname"] == "alice"
    assert row["player2_nickname"] == "bob"
    assert row["player1_score"] == "6"
    assert row["player2_score"] == "3"


async def test_player_edit_and_delete_singles_match(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]
    match = await submit_singles_match(client, league_id)

    edit_resp = await client.patch(
        f"/leagues/{league_id}/singles-matches/{match['match_id']}",
        json={"player1_score": "4", "player2_score": "6"},
    )
    assert edit_resp.status_code == 200, edit_resp.text
    assert edit_resp.json()["player1_score"] == "4"
    assert edit_resp.json()["player2_score"] == "6"

    history_resp = await client.get(f"/leagues/{league_id}/matches?scope=singles")
    assert history_resp.status_code == 200, history_resp.text
    history_row = history_resp.json()["matches"][0]
    assert history_row["player1_score"] == "4"
    assert history_row["player2_score"] == "6"

    delete_resp = await client.delete(
        f"/leagues/{league_id}/singles-matches/{match['match_id']}"
    )
    assert delete_resp.status_code == 204

    empty_history_resp = await client.get(f"/leagues/{league_id}/matches?scope=singles")
    assert empty_history_resp.status_code == 200, empty_history_resp.text
    assert empty_history_resp.json()["matches"] == []


async def test_admin_edit_and_delete_singles_match(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]
    host_token = league["host_token"]
    match = await submit_singles_match(client, league_id)

    edit_resp = await client.patch(
        f"/admin/leagues/{league_id}/singles-matches/{match['match_id']}",
        json={"player1_score": "7", "player2_score": "5"},
        headers={"X-Host-Token": host_token},
    )
    assert edit_resp.status_code == 200, edit_resp.text
    assert edit_resp.json()["player1_score"] == "7"
    assert edit_resp.json()["player2_score"] == "5"

    delete_resp = await client.delete(
        f"/admin/leagues/{league_id}/singles-matches/{match['match_id']}",
        headers={"X-Host-Token": host_token},
    )
    assert delete_resp.status_code == 204

    history_resp = await client.get(f"/leagues/{league_id}/matches?scope=singles")
    assert history_resp.status_code == 200, history_resp.text
    assert history_resp.json()["matches"] == []

