"""E2E tests for the admin-only API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_HOST_EMAIL = "glhf0825@gmail.com"


async def create_league(
    client: AsyncClient,
    title: str = "Admin Test League",
    host_email: str = _DEFAULT_HOST_EMAIL,
) -> dict:
    resp = await client.post(
        "/leagues", json={"title": title, "host_email": host_email}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def submit_match(
    client: AsyncClient,
    league_id: str,
    pair1: tuple[str, str] = ("alice", "bob"),
    pair2: tuple[str, str] = ("charlie", "diana"),
    pair1_score: str = "6",
    pair2_score: str = "3",
) -> dict:
    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": list(pair1),
            "pair2_nicknames": list(pair2),
            "pair1_score": pair1_score,
            "pair2_score": pair2_score,
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


async def get_pair_id(
    client: AsyncClient, league_id: str, p1: str, p2: str
) -> str:
    roster = await get_roster(client, league_id)
    expected_pair = {p1, p2}
    for roster_pair in roster["pairs"]:
        if {
            roster_pair["player1_nickname"],
            roster_pair["player2_nickname"],
        } == expected_pair:
            return roster_pair["pair_id"]
    raise AssertionError(f"Pair ({p1}, {p2}) not found in roster")


# ---------------------------------------------------------------------------
# GET /admin/leagues/{league_id}
# ---------------------------------------------------------------------------


async def test_get_league_admin_info_returns_host_email(client: AsyncClient) -> None:
    league = await create_league(client, host_email="admin@example.com")
    league_id = league["league_id"]
    host_token = league["host_token"]

    resp = await client.get(
        f"/admin/leagues/{league_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"host_email": "admin@example.com"}


async def test_get_league_admin_info_missing_token_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    resp = await client.get(f"/admin/leagues/{league['league_id']}")
    assert resp.status_code == 422


async def test_get_league_admin_info_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    resp = await client.get(
        f"/admin/leagues/{league['league_id']}",
        headers={"X-Host-Token": "not-the-token"},
    )
    assert resp.status_code == 401


async def test_get_league_admin_info_league_not_found_returns_404(
    client: AsyncClient,
) -> None:
    resp = await client.get(
        "/admin/leagues/00000000-0000-0000-0000-000000000099",
        headers={"X-Host-Token": "any-token"},
    )
    assert resp.status_code == 404


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


async def test_update_player_rating_persists(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    player_id = await get_player_id(client, league_id, "alice")

    resp = await client.patch(
        f"/admin/leagues/{league_id}/players/{player_id}",
        json={"rating": 3.5},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["player_id"] == player_id
    assert body["new_nickname"] == "alice"
    assert body["rating"] == 3.5

    roster = await get_roster(client, league_id)
    alice = next(p for p in roster["players"] if p["player_id"] == player_id)
    assert alice["rating"] == 3.5


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/pairs/{pair_id}
# ---------------------------------------------------------------------------


async def test_delete_pair_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    # Submit a match so pair exists; then delete the only match so pair has no matches
    match = await submit_match(client, league_id)
    match_id = match["match_id"]
    pair_id = await get_pair_id(client, league_id, "alice", "bob")

    # Delete the match first so the pair has no match records
    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        headers={"X-Host-Token": host_token},
    )

    resp = await client.delete(
        f"/admin/leagues/{league_id}/pairs/{pair_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 204


async def test_delete_pair_success_removes_from_roster(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id)
    pair_id = await get_pair_id(client, league_id, "alice", "bob")

    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        headers={"X-Host-Token": host_token},
    )
    await client.delete(
        f"/admin/leagues/{league_id}/pairs/{pair_id}",
        headers={"X-Host-Token": host_token},
    )

    roster = await get_roster(client, league_id)
    pair_ids = {t["pair_id"] for t in roster["pairs"]}
    assert pair_id not in pair_ids


async def test_delete_pair_with_matches_returns_409(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    pair_id = await get_pair_id(client, league_id, "alice", "bob")

    resp = await client.delete(
        f"/admin/leagues/{league_id}/pairs/{pair_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "PairHasMatchesError"


async def test_delete_pair_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)
    pair_id = await get_pair_id(client, league_id, "alice", "bob")

    await client.delete(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        headers={"X-Host-Token": league["host_token"]},
    )

    resp = await client.delete(
        f"/admin/leagues/{league_id}/pairs/{pair_id}",
        headers={"X-Host-Token": "wrong-token"},
    )

    assert resp.status_code == 401
    assert resp.json()["error"] == "UnauthorizedError"


async def test_delete_pair_not_found_returns_404(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_pair_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(
        f"/admin/leagues/{league_id}/pairs/{fake_pair_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "PairNotFoundError"


async def test_delete_pair_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.delete(
        f"/admin/leagues/{fake_id}/pairs/{fake_id}",
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

    match = await submit_match(client, league_id, pair1_score="6", pair2_score="3")
    match_id = match["match_id"]

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"pair1_score": "7", "pair2_score": "5"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["match_id"] == match_id
    assert body["pair1_score"] == "7"
    assert body["pair2_score"] == "5"


async def test_edit_match_score_persists(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    match = await submit_match(client, league_id, pair1_score="6", pair2_score="3")
    match_id = match["match_id"]

    await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"pair1_score": "2", "pair2_score": "6"},
        headers={"X-Host-Token": host_token},
    )

    history_resp = await client.get(f"/leagues/{league_id}/matches")
    history = history_resp.json()["matches"]
    updated = next(m for m in history if m["match_id"] == match_id)
    assert updated["pair1_score"] == "2"
    assert updated["pair2_score"] == "6"


async def test_edit_match_score_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(client, league_id)

    resp = await client.patch(
        f"/admin/leagues/{league_id}/matches/{match['match_id']}",
        json={"pair1_score": "7", "pair2_score": "5"},
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
        json={"pair1_score": "abc", "pair2_score": "5"},
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
        json={"pair1_score": "-1", "pair2_score": "5"},
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
        json={"pair1_score": "6", "pair2_score": "4"},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "MatchNotFoundError"


async def test_edit_match_score_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await client.patch(
        f"/admin/leagues/{fake_id}/matches/{fake_id}",
        json={"pair1_score": "6", "pair2_score": "4"},
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
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )
    match_id = match["match_id"]

    standings_before = (await client.get(f"/leagues/{league_id}/standings")).json()["standings"]
    winner_before = standings_before[0]
    alice_bob_players = {"alice", "bob"}
    assert {winner_before["player1_nickname"], winner_before["player2_nickname"]} == alice_bob_players

    # Flip the score so charlie+diana now win
    await client.patch(
        f"/admin/leagues/{league_id}/matches/{match_id}",
        json={"pair1_score": "2", "pair2_score": "6"},
        headers={"X-Host-Token": host_token},
    )

    standings_after = (await client.get(f"/leagues/{league_id}/standings")).json()["standings"]
    winner_after = standings_after[0]
    assert {winner_after["player1_nickname"], winner_after["player2_nickname"]} == {"charlie", "diana"}


async def _create_strict_roster_league(
    client: AsyncClient,
    title: str = "Strict Roster League",
) -> dict:
    """Create a league with `auto_register_players_on_match=False` so that
    match submission requires nicknames to already be on the roster."""
    resp = await client.post(
        "/leagues",
        json={
            "title": title,
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": False,
            },
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_add_players_to_roster_success(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["Alex", "Daniel", "Jason"]},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["players"]) == 3
    nicknames = {p["nickname"] for p in body["players"]}
    assert nicknames == {"alex", "daniel", "jason"}


async def test_add_players_to_roster_accepts_ratings(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={
            "players": [
                {"nickname": "Alex", "rating": 3.5},
                {"nickname": "Daniel", "rating": None},
            ]
        },
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    ratings = {p["nickname"]: p["rating"] for p in body["players"]}
    assert ratings == {"alex": 3.5, "daniel": None}

    roster = await get_roster(client, league_id)
    roster_ratings = {p["nickname"]: p["rating"] for p in roster["players"]}
    assert roster_ratings == {"alex": 3.5, "daniel": None}


async def test_add_players_makes_them_match_eligible(client: AsyncClient) -> None:
    """With `auto_register_players_on_match=False`, only pre-registered
    roster players can appear on a match. After `add_players`, those
    nicknames must be accepted by `/leagues/{id}/matches`."""
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice", "bob", "carol", "dave"]},
        headers={"X-Host-Token": host_token},
    )

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["carol", "dave"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )
    assert resp.status_code == 201, resp.text


async def test_match_submission_rejected_when_player_not_on_roster(
    client: AsyncClient,
) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice", "bob"]},
        headers={"X-Host-Token": host_token},
    )

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["carol", "dave"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "RosterMembershipRequiredError"
    assert set(body["missing_nicknames"]) == {"carol", "dave"}


async def test_add_players_duplicate_nickname_returns_409(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice"]},
        headers={"X-Host-Token": host_token},
    )

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["ALICE"]},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "NicknameAlreadyInUseError"


async def test_player_alias_lifecycle_and_alias_lookup(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    add_resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice", "bob", "charlie", "diana"]},
        headers={"X-Host-Token": host_token},
    )
    alice_id = next(
        p["player_id"] for p in add_resp.json()["players"] if p["nickname"] == "alice"
    )

    alias_resp = await client.post(
        f"/admin/leagues/{league_id}/players/{alice_id}/aliases",
        json={"alias": "Ali"},
        headers={"X-Host-Token": host_token},
    )
    assert alias_resp.status_code == 201, alias_resp.text
    assert alias_resp.json()["aliases"] == ["ali"]

    roster = await get_roster(client, league_id)
    alice = next(p for p in roster["players"] if p["nickname"] == "alice")
    assert alice["aliases"] == ["ali"]

    match_resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["ali", "bob"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )
    assert match_resp.status_code == 201, match_resp.text

    history_resp = await client.get(
        f"/leagues/{league_id}/matches/by-player",
        params={"player_name": "ali"},
    )
    assert history_resp.status_code == 200, history_resp.text
    assert history_resp.json()["matches"][0]["pair1_player1_nickname"] == "alice"

    remove_resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{alice_id}/aliases/ali",
        headers={"X-Host-Token": host_token},
    )
    assert remove_resp.status_code == 204

    final_roster = await get_roster(client, league_id)
    final_alice = next(p for p in final_roster["players"] if p["nickname"] == "alice")
    assert final_alice["aliases"] == []


async def test_add_player_rejects_collision_with_existing_alias(
    client: AsyncClient,
) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    add_resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice"]},
        headers={"X-Host-Token": host_token},
    )
    alice_id = add_resp.json()["players"][0]["player_id"]
    await client.post(
        f"/admin/leagues/{league_id}/players/{alice_id}/aliases",
        json={"alias": "ali"},
        headers={"X-Host-Token": host_token},
    )

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["ALI"]},
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "NicknameAlreadyInUseError"


async def test_remove_canonical_alias_returns_422(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    add_resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alice"]},
        headers={"X-Host-Token": host_token},
    )
    alice_id = add_resp.json()["players"][0]["player_id"]

    resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{alice_id}/aliases/alice",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "CannotRemoveCanonicalNicknameError"


async def test_add_players_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_add_players_missing_token_returns_422(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alex"]},
    )
    assert resp.status_code == 422


async def test_add_players_empty_list_returns_422(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": []},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 422


async def test_remove_player_from_roster_success(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    add_resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alex", "daniel"]},
        headers={"X-Host-Token": host_token},
    )
    alex_id = next(
        p["player_id"] for p in add_resp.json()["players"] if p["nickname"] == "alex"
    )

    resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{alex_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 204

    roster = await get_roster(client, league_id)
    nicknames = {p["nickname"] for p in roster["players"]}
    assert nicknames == {"daniel"}


async def test_remove_player_with_pair_returns_409(client: AsyncClient) -> None:
    """A player who already has a pair (and therefore likely matches)
    cannot be hard-deleted — the API surfaces a 409 with the
    `PlayerHasParticipationError` payload."""
    league = await create_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    await submit_match(client, league_id)
    alice_id = await get_player_id(client, league_id, "alice")

    resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{alice_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "PlayerHasParticipationError"
    assert body["pairs_count"] >= 1
    assert body["matches_count"] >= 1


async def test_remove_player_wrong_token_returns_401(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]

    add_resp = await client.post(
        f"/admin/leagues/{league_id}/players",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": host_token},
    )
    player_id = add_resp.json()["players"][0]["player_id"]

    resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{player_id}",
        headers={"X-Host-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_remove_player_not_found_returns_404(client: AsyncClient) -> None:
    league = await _create_strict_roster_league(client)
    league_id, host_token = league["league_id"], league["host_token"]
    fake_player_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(
        f"/admin/leagues/{league_id}/players/{fake_player_id}",
        headers={"X-Host-Token": host_token},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "PlayerNotFoundError"
