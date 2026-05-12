"""E2E tests for the eligible-players API surface (v4 feature).

Three scenarios anchor the suite:

1. Host-managed flow: create league → add → list → remove → list.
2. Rule-on rejection: a league created with `require_eligible_players=true`
   rejects match submission when participants are not in the eligible list,
   and the response body carries the structured `missing_nicknames` array.
3. Rule-off no-op: the default league (`require_eligible_players=false`)
   accepts match submissions even when the eligible list is empty —
   backwards-compatibility for every league that existed before this
   feature.
"""
from __future__ import annotations

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers (kept local so the file is self-contained)
# ---------------------------------------------------------------------------


async def _create_league(
    client: AsyncClient,
    title: str,
    require_eligible_players: bool = False,
) -> dict:
    body: dict = {"title": title}
    if require_eligible_players:
        body["rules"] = {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
    resp = await client.post("/leagues", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _submit_match(
    client: AsyncClient,
    league_id: str,
    team1=("alice", "bob"),
    team2=("charlie", "diana"),
):
    return await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": list(team1),
            "team2_nicknames": list(team2),
            "team1_score": "6",
            "team2_score": "3",
        },
    )


# ---------------------------------------------------------------------------
# Scenario 1: host-managed flow (add → list → remove → list)
# ---------------------------------------------------------------------------


async def test_host_can_add_list_and_remove_eligible_players(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Host Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    # Initially empty.
    resp = await client.get(f"/leagues/{league_id}/eligible-players")
    assert resp.status_code == 200
    assert resp.json() == {"eligible_players": []}

    # Add three nicknames atomically.
    resp = await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["Alex", "Daniel", "Jason"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [e["nickname"] for e in body["eligible_players"]] == [
        "alex",
        "daniel",
        "jason",
    ]
    alex_id = next(
        e["eligible_player_id"]
        for e in body["eligible_players"]
        if e["nickname"] == "alex"
    )

    # List shows all three (sorted alphabetically).
    resp = await client.get(f"/leagues/{league_id}/eligible-players")
    assert resp.status_code == 200
    nicks = [e["nickname"] for e in resp.json()["eligible_players"]]
    assert nicks == ["alex", "daniel", "jason"]

    # Remove "alex" by id.
    resp = await client.delete(
        f"/admin/leagues/{league_id}/eligible-players/{alex_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 204

    resp = await client.get(f"/leagues/{league_id}/eligible-players")
    nicks = [e["nickname"] for e in resp.json()["eligible_players"]]
    assert nicks == ["daniel", "jason"]


async def test_add_eligible_players_duplicate_returns_409(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Dup Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": host_token},
    )
    resp = await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["ALEX"]},  # case-insensitive duplicate
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "EligiblePlayerNicknameAlreadyExistsError"


async def test_add_eligible_players_wrong_token_returns_401(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Auth Flow League")
    league_id = league["league_id"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_remove_unknown_eligible_player_returns_404(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "404 Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.delete(
        f"/admin/leagues/{league_id}/eligible-players/{fake_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "EligiblePlayerNotFoundError"


async def test_get_eligible_players_unknown_league_returns_404(
    client: AsyncClient,
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/eligible-players")
    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# Scenario 2: rule-on rejection at match submission
# ---------------------------------------------------------------------------


async def test_match_submission_rejected_when_participants_not_eligible(
    client: AsyncClient,
) -> None:
    league = await _create_league(
        client, "Allowlist League", require_eligible_players=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    # Allowlist only two of the four submitting players.
    resp = await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alice", "bob"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201

    # Submit a match with two ineligible participants → 422 with structured
    # missing_nicknames so the chat agent / frontend can render them verbatim.
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "IneligiblePlayerError"
    assert sorted(body["missing_nicknames"]) == ["charlie", "diana"]


async def test_match_submission_succeeds_when_all_participants_eligible(
    client: AsyncClient,
) -> None:
    league = await _create_league(
        client, "Allowlist Happy League", require_eligible_players=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alice", "bob", "charlie", "diana"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201

    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text
    assert "match_id" in resp.json()


async def test_match_submission_rejection_normalizes_input(
    client: AsyncClient,
) -> None:
    """Mixed-case input must be normalized before matching against the eligible
    list, otherwise hosts who add `Alice` to the allowlist would still see
    matches recorded with `ALICE` rejected."""
    league = await _create_league(
        client, "Normalize League", require_eligible_players=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alice", "bob", "charlie", "diana"]},
        headers={"X-Host-Token": host_token},
    )

    resp = await _submit_match(
        client,
        league_id,
        team1=("Alice", "BOB"),
        team2=(" Charlie ", "diana"),
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Scenario 3: rule-off no-op (backwards compat)
# ---------------------------------------------------------------------------


async def test_default_league_does_not_enforce_eligible_check(
    client: AsyncClient,
) -> None:
    """The default rules carry require_eligible_players=False, so submitting
    a match against an empty eligible list must succeed — preserves byte-for-
    byte compatibility for every league that existed before this feature."""
    league = await _create_league(client, "Default League")
    league_id = league["league_id"]

    # Eligible list is empty.
    resp = await client.get(f"/leagues/{league_id}/eligible-players")
    assert resp.status_code == 200
    assert resp.json() == {"eligible_players": []}

    # Match submission still succeeds.
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text


async def test_default_league_with_eligible_entries_still_does_not_block(
    client: AsyncClient,
) -> None:
    """Even when the host populates the eligible list on a default league
    (require_eligible_players=False), the list is informational only — match
    submission must NOT be gated on it."""
    league = await _create_league(client, "Informational League")
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/eligible-players",
        json={"nicknames": ["alice"]},  # only one of the four participants
        headers={"X-Host-Token": host_token},
    )

    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text
