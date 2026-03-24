"""E2E tests for the admin-only API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def create_league(
    client: AsyncClient,
    title: str = "Admin Test League",
) -> dict:
    resp = await client.post("/leagues", json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def submit_match(
    client: AsyncClient,
    league_id: str,
    team1: tuple[str, str] = ("alice", "bob"),
    team2: tuple[str, str] = ("charlie", "diana"),
    team1_score: str = "6",
    team2_score: str = "3",
) -> dict:
    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": list(team1),
            "team2_nicknames": list(team2),
            "team1_score": team1_score,
            "team2_score": team2_score,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def get_roster(client: AsyncClient, league_id: str) -> dict:
    resp = await client.get(f"/leagues/{league_id}/roster")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def get_player_id(client: AsyncClient, league_id: str, nickname: str) -> str:
    roster = await get_roster(client, league_id)
    for player in roster["players"]:
        if player["nickname"] == nickname:
            return player["player_id"]
    raise AssertionError(f"Player '{nickname}' not found in roster")


async def get_team_id(
    client: AsyncClient, league_id: str, p1: str, p2: str
) -> str:
    roster = await get_roster(client, league_id)
    pair = {p1, p2}
    for team in roster["teams"]:
        if {team["player1_nickname"], team["player2_nickname"]} == pair:
            return team["team_id"]
    raise AssertionError(f"Team ({p1}, {p2}) not found in roster")


# ---------------------------------------------------------------------------
# PATCH /admin/leagues/{league_id}/players/{player_id}
# ---------------------------------------------------------------------------


async def test_edit_player_nickname_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "Ace"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["player_id"] == player_id
    assert body["new_nickname"] == "ace"  # normalized to lowercase


async def test_edit_player_nickname_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "Ace"},
        headers={"X-Host-Token": "wrong-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "UnauthorizedError"


async def test_edit_player_nickname_missing_token_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "Ace"},
    )

    assert resp.status_code == 422


async def test_edit_player_nickname_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.patch(
        f"/admin/leagues/{fake_id}/players/{fake_id}",
        json={"new_nickname": "Ace"},
        headers={"X-Host-Token": "any-token"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_edit_player_nickname_player_not_found(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_player_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{fake_player_id}",
        json={"new_nickname": "Ace"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "PlayerNotFoundError"


async def test_edit_player_nickname_duplicate_returns_409(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    # Try to rename alice → bob (bob already exists)
    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "bob"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "NicknameAlreadyInUseError"


async def test_edit_player_nickname_blank_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "   "},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 422


async def test_edit_player_nickname_persists(client: AsyncClient) -> None:
    """Verify the rename is visible in subsequent roster queries."""
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"new_nickname": "Serena"},
        headers={"X-Host-Token": host_token},
    )

    roster = await get_roster(client, league_id)
    nicknames = {p["nickname"] for p in roster["players"]}
    assert "serena" in nicknames
    assert "alice" not in nicknames


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/teams/{team_id}
# ---------------------------------------------------------------------------


async def test_delete_team_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    # Submit a match so team exists; then delete the only match so team has no matches
    match = await submit_match(client, league_id)
    match_id = match["match_id"]
    team_id = await get_team_id(client, league_id, "alice", "bob")

    # Delete the match first so the team has no match records
    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        headers={"X-Host-Token": host_token},
    )

    resp = await client.delete(
        f"/admin/leagues/{league_id}/teams/{team_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 204


async def test_delete_team_success_removes_from_roster(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)
    team_id = await get_team_id(client, league_id, "alice", "bob")

    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        headers={"X-Host-Token": host_token},
    )
    await client.delete(
        f"/admin/leagues/{league_id}/teams/{team_id}",
        headers={"X-Host-Token": host_token},
    )

    roster = await get_roster(client, league_id)
    team_ids = {t["team_id"] for t in roster["teams"]}
    assert team_id not in team_ids


async def test_delete_team_with_matches_returns_409(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    team_id = await get_team_id(client, league_id, "alice", "bob")

    resp = await client.delete(
        f"/admin/leagues/{league_id}/teams/{team_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "TeamHasMatchesError"


async def test_delete_team_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)
    team_id = await get_team_id(client, league_id, "alice", "bob")

    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        headers={"X-Host-Token": league["host_token"]},
    )

    resp = await client.delete(
        f"/admin/leagues/{league_id}/teams/{team_id}",
        headers={"X-Host-Token": "wrong-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "UnauthorizedError"


async def test_delete_team_not_found_returns_404(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_team_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(
        f"/admin/leagues/{league_id}/teams/{fake_team_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "TeamNotFoundError"


async def test_delete_team_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.delete(
        f"/admin/leagues/{fake_id}/teams/{fake_id}",
        headers={"X-Host-Token": "any-token"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# PATCH /admin/leagues/{league_id}/matches/{match_id}
# ---------------------------------------------------------------------------


async def test_edit_match_score_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id, team1_score="6", team2_score="3")
    match_id = match["match_id"]

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "7", "team2_score": "5"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match_id"] == match_id
    assert body["team1_score"] == "7"
    assert body["team2_score"] == "5"


async def test_edit_match_score_persists(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id, team1_score="6", team2_score="3")
    match_id = match["match_id"]

    await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "2", "team2_score": "6"},
        headers={"X-Host-Token": host_token},
    )

    history_resp = await client.get(f"/leagues/{league_id}/matches")
    history = history_resp.json()["matches"]
    updated = next(m for m in history if m["match_id"] == match_id)
    assert updated["team1_score"] == "2"
    assert updated["team2_score"] == "6"


async def test_edit_match_score_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        json={"team1_score": "7", "team2_score": "5"},
        headers={"X-Host-Token": "wrong-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "UnauthorizedError"


async def test_edit_match_score_invalid_score_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        json={"team1_score": "abc", "team2_score": "5"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_edit_match_score_negative_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        json={"team1_score": "-1", "team2_score": "5"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_edit_match_score_match_not_found_returns_404(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{fake_match_id}",
        json={"team1_score": "6", "team2_score": "4"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "MatchNotFoundError"


async def test_edit_match_score_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.patch(
        f"/admin/leagues/{fake_id}/matches/{fake_id}",
        json={"team1_score": "6", "team2_score": "4"},
        headers={"X-Host-Token": "any-token"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/matches/{match_id}
# ---------------------------------------------------------------------------


async def test_delete_match_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)
    match_id = match["match_id"]

    resp = await client.delete(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 204


async def test_delete_match_removes_from_history(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)
    match_id = match["match_id"]

    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        headers={"X-Host-Token": host_token},
    )

    history_resp = await client.get(f"/leagues/{league_id}/matches")
    match_ids = [m["match_id"] for m in history_resp.json()["matches"]]
    assert match_id not in match_ids


async def test_delete_match_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)

    resp = await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        headers={"X-Host-Token": "wrong-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "UnauthorizedError"


async def test_delete_match_not_found_returns_404(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(
        f"/admin/leagues/{league_id}/matches/{fake_match_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "MatchNotFoundError"


async def test_delete_match_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.delete(
        f"/admin/leagues/{fake_id}/matches/{fake_id}",
        headers={"X-Host-Token": "any-token"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_delete_match_missing_token_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)

    resp = await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cross-concern: standings update after admin edits
# ---------------------------------------------------------------------------


async def test_standings_update_after_score_edit(client: AsyncClient) -> None:
    """After editing a score so the winner flips, standings should reflect the new winner."""
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(
        client, league_id,
        team1=("alice", "bob"),
        team2=("charlie", "diana"),
        team1_score="6",
        team2_score="3",
    )
    match_id = match["match_id"]

    standings_before = (await client.get(f"/leagues/{league_id}/standings")).json()["standings"]
    winner_before = standings_before[0]
    alice_bob_players = {"alice", "bob"}
    assert {winner_before["player1_nickname"], winner_before["player2_nickname"]} == alice_bob_players

    # Flip the score so charlie+diana now win
    await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "2", "team2_score": "6"},
        headers={"X-Host-Token": host_token},
    )

    standings_after = (await client.get(f"/leagues/{league_id}/standings")).json()["standings"]
    winner_after = standings_after[0]
    assert {winner_after["player1_nickname"], winner_after["player2_nickname"]} == {"charlie", "diana"}
