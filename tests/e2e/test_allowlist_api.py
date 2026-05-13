"""E2E tests for the allowlist API surface (rules v5 feature).

Three scenarios anchor the suite:

1. Host-managed flow: create league → add → list → remove → list.
2. Rule-on rejection: a league created with `require_allowlist=true`
   rejects match submission when participants are not in the allowlist,
   and the response body carries the structured `missing_nicknames` array.
3. Rule-off no-op: the default league (`require_allowlist=false`) accepts
   match submissions even when the allowlist is empty — backwards-
   compatibility for every league that existed before this feature.
"""
from __future__ import annotations

from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers (kept local so the file is self-contained)
# ---------------------------------------------------------------------------


async def _create_league(
    client: AsyncClient,
    title: str,
    require_allowlist: bool = False,
) -> dict:
    body: dict = {"title": title}
    if require_allowlist:
        body["rules"] = {
            "version": 5,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
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


async def test_host_can_add_list_and_remove_allowlist_entries(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Host Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    # Initially empty.
    resp = await client.get(f"/leagues/{league_id}/allowlist")
    assert resp.status_code == 200
    assert resp.json() == {"allowlist": []}

    # Add three nicknames atomically.
    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["Alex", "Daniel", "Jason"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert [e["nickname"] for e in body["allowlist"]] == [
        "alex",
        "daniel",
        "jason",
    ]
    alex_id = next(
        e["allowlist_entry_id"]
        for e in body["allowlist"]
        if e["nickname"] == "alex"
    )

    # List shows all three (sorted alphabetically).
    resp = await client.get(f"/leagues/{league_id}/allowlist")
    assert resp.status_code == 200
    nicks = [e["nickname"] for e in resp.json()["allowlist"]]
    assert nicks == ["alex", "daniel", "jason"]

    # Remove "alex" by id.
    resp = await client.delete(
        f"/admin/leagues/{league_id}/allowlist/{alex_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 204

    resp = await client.get(f"/leagues/{league_id}/allowlist")
    nicks = [e["nickname"] for e in resp.json()["allowlist"]]
    assert nicks == ["daniel", "jason"]


async def test_add_allowlist_entries_duplicate_returns_409(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Dup Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": host_token},
    )
    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["ALEX"]},  # case-insensitive duplicate
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] == "AllowlistNicknameAlreadyExistsError"


async def test_add_allowlist_entries_wrong_token_returns_401(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "Auth Flow League")
    league_id = league["league_id"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["alex"]},
        headers={"X-Host-Token": "wrong-token"},
    )
    assert resp.status_code == 401


async def test_remove_unknown_allowlist_entry_returns_404(
    client: AsyncClient,
) -> None:
    league = await _create_league(client, "404 Flow League")
    league_id, host_token = league["league_id"], league["host_token"]

    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.delete(
        f"/admin/leagues/{league_id}/allowlist/{fake_id}",
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "AllowlistEntryNotFoundError"


async def test_get_allowlist_unknown_league_returns_404(
    client: AsyncClient,
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/allowlist")
    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# Scenario 2: rule-on rejection at match submission
# ---------------------------------------------------------------------------


async def test_match_submission_rejected_when_participants_not_allowlisted(
    client: AsyncClient,
) -> None:
    league = await _create_league(
        client, "Allowlist League", require_allowlist=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    # Allowlist only two of the four submitting players.
    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["alice", "bob"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201

    # Submit a match with two participants not on the allowlist → 422 with
    # structured missing_nicknames so the chat agent / frontend can render
    # them verbatim.
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "NotInAllowlistError"
    assert sorted(body["missing_nicknames"]) == ["charlie", "diana"]


async def test_match_submission_succeeds_when_all_participants_allowlisted(
    client: AsyncClient,
) -> None:
    league = await _create_league(
        client, "Allowlist Happy League", require_allowlist=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
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
    """Mixed-case input must be normalized before matching against the
    allowlist, otherwise hosts who add `Alice` to the allowlist would still
    see matches recorded with `ALICE` rejected."""
    league = await _create_league(
        client, "Normalize League", require_allowlist=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/allowlist",
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


async def test_default_league_does_not_enforce_allowlist_check(
    client: AsyncClient,
) -> None:
    """The default rules carry require_allowlist=False, so submitting a match
    against an empty allowlist must succeed — preserves byte-for-byte
    compatibility for every league that existed before this feature."""
    league = await _create_league(client, "Default League")
    league_id = league["league_id"]

    # Allowlist is empty.
    resp = await client.get(f"/leagues/{league_id}/allowlist")
    assert resp.status_code == 200
    assert resp.json() == {"allowlist": []}

    # Match submission still succeeds.
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text


async def test_default_league_with_allowlist_entries_still_does_not_block(
    client: AsyncClient,
) -> None:
    """Even when the host populates the allowlist on a default league
    (require_allowlist=False), the list is informational only — match
    submission must NOT be gated on it."""
    league = await _create_league(client, "Informational League")
    league_id, host_token = league["league_id"], league["host_token"]

    await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["alice"]},  # only one of the four participants
        headers={"X-Host-Token": host_token},
    )

    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text
