"""E2E tests for the public League API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def create_league(
    client: AsyncClient,
    title: str = "Test League",
    description: str | None = None,
) -> dict:
    payload: dict = {"title": title}
    if description is not None:
        payload["description"] = description
    resp = await client.post("/leagues", json=payload)
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


# ---------------------------------------------------------------------------
# POST /leagues
# ---------------------------------------------------------------------------


async def test_create_league_success(client: AsyncClient) -> None:
    resp = await client.post("/leagues", json={"title": "Summer Open 2026"})

    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body
    assert len(body["league_id"]) == 36  # UUID format
    assert body["host_token"]


async def test_create_league_with_description(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={"title": "Autumn Cup", "description": "Annual autumn tournament"},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body


async def test_create_league_duplicate_title_returns_409(client: AsyncClient) -> None:
    await create_league(client, title="Unique League")

    resp = await client.post("/leagues", json={"title": "Unique League"})

    assert resp.status_code == 409
    assert resp.json()["error"] == "LeagueTitleAlreadyExistsError"


async def test_create_league_duplicate_title_case_insensitive(client: AsyncClient) -> None:
    await create_league(client, title="Grand Slam")

    resp = await client.post("/leagues", json={"title": "grand slam"})

    assert resp.status_code == 409
    assert resp.json()["error"] == "LeagueTitleAlreadyExistsError"


async def test_create_league_blank_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/leagues", json={"title": "   "})

    assert resp.status_code == 422


async def test_create_league_empty_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/leagues", json={"title": ""})

    assert resp.status_code == 422


async def test_create_league_missing_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/leagues", json={})

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


async def test_submit_match_result_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "6",
            "team2_score": "4",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "match_id" in body
    assert len(body["match_id"]) == 36


async def test_submit_match_result_creates_players_and_teams(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))

    roster_resp = await client.get(f"/leagues/{league_id}/roster")
    assert roster_resp.status_code == 200
    roster = roster_resp.json()
    nicknames = {p["nickname"] for p in roster["players"]}
    assert nicknames == {"alice", "bob", "charlie", "diana"}
    assert len(roster["teams"]) == 2


async def test_submit_match_same_players_different_matches(client: AsyncClient) -> None:
    """Reusing the same player pair on two separate matches reuses the same team."""
    league = await create_league(client)
    league_id = league["league_id"]

    match1 = await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))
    match2 = await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))

    assert match1["match_id"] != match2["match_id"]

    roster_resp = await client.get(f"/leagues/{league_id}/roster")
    roster = roster_resp.json()
    assert len(roster["teams"]) == 2  # no duplicate teams created


async def test_submit_match_result_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"/leagues/{fake_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_submit_match_result_invalid_score_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "abc",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_submit_match_result_negative_score_returns_422(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "-1",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_submit_match_result_same_player_within_team_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "alice"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "SamePlayerWithinSingleTeamError"


async def test_submit_match_result_same_player_on_both_teams_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["alice", "charlie"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "SamePlayerOnBothTeamsError"


async def test_submit_match_result_player_already_in_another_team_returns_409(
    client: AsyncClient,
) -> None:
    """Alice is already paired with bob; pairing her with charlie should be rejected."""
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "charlie"],
            "team2_nicknames": ["eve", "frank"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "TeamConflictError"


async def test_submit_match_result_team1_missing_one_player_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )

    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/standings
# ---------------------------------------------------------------------------


async def test_get_standings_empty_league(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.get(f"/leagues/{league_id}/standings")

    assert resp.status_code == 200
    body = resp.json()
    assert body["standings"] == []


async def test_get_standings_after_match(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(
        client,
        league_id,
        team1=("alice", "bob"),
        team2=("charlie", "diana"),
        team1_score="6",
        team2_score="3",
    )

    resp = await client.get(f"/leagues/{league_id}/standings")

    assert resp.status_code == 200
    standings = resp.json()["standings"]
    assert len(standings) == 2

    first = standings[0]
    assert first["rank"] == 1
    assert first["wins"] == 1
    assert first["losses"] == 0

    second = standings[1]
    assert second["rank"] == 2
    assert second["wins"] == 0
    assert second["losses"] == 1


async def test_get_standings_multiple_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    # alice+bob win 2 matches, charlie+diana win 1
    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"), team1_score="6", team2_score="3")
    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"), team1_score="7", team2_score="5")
    await submit_match(client, league_id, team1=("charlie", "diana"), team2=("alice", "bob"), team1_score="6", team2_score="2")

    resp = await client.get(f"/leagues/{league_id}/standings")

    assert resp.status_code == 200
    standings = resp.json()["standings"]
    assert standings[0]["wins"] == 2
    assert standings[0]["losses"] == 1
    assert standings[1]["wins"] == 1
    assert standings[1]["losses"] == 2


async def test_get_standings_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/standings")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


async def test_get_match_history_empty(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.get(f"/leagues/{league_id}/matches")

    assert resp.status_code == 200
    assert resp.json()["matches"] == []


async def test_get_match_history_after_match(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(
        client,
        league_id,
        team1=("alice", "bob"),
        team2=("charlie", "diana"),
        team1_score="6",
        team2_score="4",
    )

    resp = await client.get(f"/leagues/{league_id}/matches")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1

    record = matches[0]
    assert record["match_id"] == match["match_id"]
    assert record["team1_score"] == "6"
    assert record["team2_score"] == "4"
    assert set(
        [record["team1_player1_nickname"], record["team1_player2_nickname"]]
    ) == {"alice", "bob"}
    assert set(
        [record["team2_player1_nickname"], record["team2_player2_nickname"]]
    ) == {"charlie", "diana"}
    assert record["created_at"] is not None


async def test_get_match_history_multiple_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))
    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"), team1_score="4", team2_score="6")

    resp = await client.get(f"/leagues/{league_id}/matches")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 2


async def test_get_match_history_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/matches")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/roster
# ---------------------------------------------------------------------------


async def test_get_league_roster_empty(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.get(f"/leagues/{league_id}/roster")

    assert resp.status_code == 200
    body = resp.json()
    assert body["players"] == []
    assert body["teams"] == []


async def test_get_league_roster_after_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, team1=("alice", "bob"), team2=("charlie", "diana"))

    resp = await client.get(f"/leagues/{league_id}/roster")

    assert resp.status_code == 200
    body = resp.json()

    assert len(body["players"]) == 4
    nicknames = {p["nickname"] for p in body["players"]}
    assert nicknames == {"alice", "bob", "charlie", "diana"}

    assert len(body["teams"]) == 2
    for team in body["teams"]:
        assert "team_id" in team
        assert "player1_nickname" in team
        assert "player2_nickname" in team


async def test_get_league_roster_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/roster")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_get_league_roster_player_ids_are_valid_uuids(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id)

    resp = await client.get(f"/leagues/{league_id}/roster")
    body = resp.json()

    import uuid

    for player in body["players"]:
        uuid.UUID(player["player_id"])  # raises ValueError if invalid

    for team in body["teams"]:
        uuid.UUID(team["team_id"])
