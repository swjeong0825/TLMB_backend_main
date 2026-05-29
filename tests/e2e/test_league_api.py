"""E2E tests for the public League API endpoints."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Default for e2e: allow rematches between the same pair matchup (most tests submit twice).
_DEFAULT_E2E_RULES = {
    "version": 8,
    "pair_matchup_idempotency": "none",
    "one_pair_per_player": True,
    "ranking_subject": "pair",
    "tie_breakers": ["matches_won"],
    "auto_register_players_on_match": True,
}

# Default host email for e2e -- matches the backfill value used in
# alembic 008 so dev-fixture data is consistent with migrated rows.
_DEFAULT_HOST_EMAIL = "glhf0825@gmail.com"


async def create_league(
    client: AsyncClient,
    title: str = "Test League",
    description: str | None = None,
    rules: dict | None = _DEFAULT_E2E_RULES,
    host_email: str = _DEFAULT_HOST_EMAIL,
    league_timezone: str | None = None,
) -> dict:
    payload: dict = {"title": title, "host_email": host_email}
    if description is not None:
        payload["description"] = description
    if league_timezone is not None:
        payload["league_timezone"] = league_timezone
    if rules is not None:
        payload["rules"] = rules
    resp = await client.post("/leagues", json=payload)
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


# ---------------------------------------------------------------------------
# POST /leagues
# ---------------------------------------------------------------------------


async def test_create_league_success(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={"title": "Summer Open 2026", "host_email": _DEFAULT_HOST_EMAIL},
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body
    assert len(body["league_id"]) == 36  # UUID format
    assert body["host_token"]
    assert "host_email" not in body  # private: not echoed on the create response


async def test_create_league_with_description(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Autumn Cup",
            "host_email": _DEFAULT_HOST_EMAIL,
            "description": "Annual autumn tournament",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body


async def test_create_league_duplicate_title_returns_409(client: AsyncClient) -> None:
    await create_league(client, title="Unique League")

    resp = await client.post(
        "/leagues",
        json={"title": "Unique League", "host_email": _DEFAULT_HOST_EMAIL},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "LeagueTitleAlreadyExistsError"


async def test_create_league_duplicate_title_case_insensitive(client: AsyncClient) -> None:
    await create_league(client, title="Grand Slam")

    resp = await client.post(
        "/leagues",
        json={"title": "grand slam", "host_email": _DEFAULT_HOST_EMAIL},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "LeagueTitleAlreadyExistsError"


async def test_create_league_blank_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={"title": "   ", "host_email": _DEFAULT_HOST_EMAIL},
    )

    assert resp.status_code == 422


async def test_create_league_empty_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={"title": "", "host_email": _DEFAULT_HOST_EMAIL},
    )

    assert resp.status_code == 422


async def test_create_league_missing_title_returns_422(client: AsyncClient) -> None:
    resp = await client.post("/leagues", json={"host_email": _DEFAULT_HOST_EMAIL})

    assert resp.status_code == 422


async def test_create_league_missing_host_email_returns_422(client: AsyncClient) -> None:
    """host_email is mandatory; Pydantic returns 422 when absent."""
    resp = await client.post("/leagues", json={"title": "No Email League"})

    assert resp.status_code == 422


async def test_create_league_malformed_host_email_returns_422(client: AsyncClient) -> None:
    """Pydantic EmailStr rejects strings that aren't valid email addresses."""
    resp = await client.post(
        "/leagues",
        json={"title": "Bad Email League", "host_email": "not-an-email"},
    )

    assert resp.status_code == 422


async def test_create_league_invalid_rules_version_returns_422(client: AsyncClient) -> None:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Bad Rules",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 7,
                "pair_matchup_idempotency": "none",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
            },
        },
    )
    assert resp.status_code == 422


async def test_create_league_invalid_league_timezone_returns_422(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Bad Timezone League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "league_timezone": "not/a-zone",
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidLeagueRulesError"


async def test_create_league_with_otpp_false_succeeds(client: AsyncClient) -> None:
    """v3 unlocks `(pair, OTPP=false)` -- a player may belong to multiple pairs.

    See backend_main/Design_Doc/TLMB_Design_doc/18_configurable_ranking_v3.md
    for the v3 cross-rule.
    """
    resp = await client.post(
        "/leagues",
        json={
            "title": "OTPP False League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": False,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won"],
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body


async def test_create_league_with_player_subject_and_otpp_true_returns_422(
    client: AsyncClient,
) -> None:
    """v3 cross-rule: `(player, OTPP=true)` is rejected."""
    resp = await client.post(
        "/leagues",
        json={
            "title": "Player OTPP True League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": True,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            },
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidLeagueRulesError"


async def test_create_league_with_player_subject_and_otpp_false_succeeds(
    client: AsyncClient,
) -> None:
    """v3: `(player, OTPP=false)` is the only legal player-subject combo."""
    resp = await client.post(
        "/leagues",
        json={
            "title": "Player OTPP False League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": False,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body


async def test_v2_rules_input_upgrades_to_v3(client: AsyncClient) -> None:
    """v2 inputs are accepted on input and upgraded transparently to v3."""
    resp = await client.post(
        "/leagues",
        json={
            "title": "V2 Upgrade Smoke Test",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["matches_won", "games_diff"],
            },
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "league_id" in body
    assert "host_token" in body


# ---------------------------------------------------------------------------
# POST /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


async def test_second_submit_same_pair_matchup_returns_409_with_default_league_rules(
    client: AsyncClient,
) -> None:
    """POST /leagues without `rules` uses product default once_per_day."""
    resp = await client.post(
        "/leagues",
        json={"title": "Single Meeting League", "host_email": _DEFAULT_HOST_EMAIL},
    )
    assert resp.status_code == 201
    league_id = resp.json()["league_id"]
    payload = {
        "pair1_nicknames": ["a", "b"],
        "pair2_nicknames": ["c", "d"],
        "pair1_score": "6",
        "pair2_score": "3",
    }
    first = await client.post(f"/leagues/{league_id}/matches", json=payload)
    assert first.status_code == 201
    second = await client.post(f"/leagues/{league_id}/matches", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "DuplicatePairMatchupMatchError"


async def test_create_league_without_rules_uses_v8_daily_default(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/leagues",
        json={"title": "Daily Default League", "host_email": _DEFAULT_HOST_EMAIL},
    )
    assert resp.status_code == 201
    league_id = resp.json()["league_id"]

    roster = await client.get(f"/leagues/{league_id}/roster")

    assert roster.status_code == 200
    body = roster.json()
    assert body["league_timezone"] == "America/Los_Angeles"
    rules = body["rules"]
    assert rules["version"] == 8
    assert rules["pair_matchup_idempotency"] == "once_per_day"


async def test_second_submit_same_pair_matchup_allowed_when_rules_allow_duplicates(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Rematch League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "none",
                "one_pair_per_player": True,
            },
        },
    )
    assert resp.status_code == 201
    league_id = resp.json()["league_id"]
    payload = {
        "pair1_nicknames": ["a", "b"],
        "pair2_nicknames": ["c", "d"],
        "pair1_score": "6",
        "pair2_score": "3",
    }
    assert (await client.post(f"/leagues/{league_id}/matches", json=payload)).status_code == 201
    assert (await client.post(f"/leagues/{league_id}/matches", json=payload)).status_code == 201


async def test_submit_match_result_success(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "6",
            "pair2_score": "4",
        },
    )

    assert resp.status_code == 201
    body = resp.json()
    assert "match_id" in body
    assert len(body["match_id"]) == 36
    # `created_at` is server-authoritative and used by the frontend to
    # gate the player-edit-window button without trusting client clocks.
    assert "created_at" in body
    assert body["created_at"]


async def test_submit_match_result_creates_players_and_pairs(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))

    roster_resp = await client.get(f"/leagues/{league_id}/roster")
    assert roster_resp.status_code == 200
    roster = roster_resp.json()
    nicknames = {p["nickname"] for p in roster["players"]}
    assert nicknames == {"alice", "bob", "charlie", "diana"}
    assert len(roster["pairs"]) == 2


async def test_submit_match_same_players_different_matches(client: AsyncClient) -> None:
    """Reusing the same player pair on two separate matches reuses the same pair."""
    league = await create_league(client)
    league_id = league["league_id"]

    match1 = await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))
    match2 = await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))

    assert match1["match_id"] != match2["match_id"]

    roster_resp = await client.get(f"/leagues/{league_id}/roster")
    roster = roster_resp.json()
    assert len(roster["pairs"]) == 2  # no duplicate pairs created


async def test_submit_match_result_league_not_found(client: AsyncClient) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.post(
        f"/leagues/{fake_id}/matches",
        json={
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "6",
            "pair2_score": "3",
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
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "abc",
            "pair2_score": "3",
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
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "-1",
            "pair2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_submit_match_result_same_player_within_pair_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "alice"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "SamePlayerWithinSinglePairError"


async def test_submit_match_result_same_player_on_both_pairs_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "bob"],
            "pair2_nicknames": ["alice", "charlie"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "SamePlayerOnBothPairsError"


async def test_submit_match_result_player_already_in_another_pair_returns_409(
    client: AsyncClient,
) -> None:
    """Alice is already paired with bob; pairing her with charlie should be rejected."""
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice", "charlie"],
            "pair2_nicknames": ["eve", "frank"],
            "pair1_score": "6",
            "pair2_score": "3",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "PairConflictError"


async def test_submit_match_result_pair1_missing_one_player_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "pair1_nicknames": ["alice"],
            "pair2_nicknames": ["charlie", "diana"],
            "pair1_score": "6",
            "pair2_score": "3",
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
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
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


async def test_get_standings_after_draw(client: AsyncClient) -> None:
    """A 5-5 set score is accepted as a draw; both pairs pick up a draw, no
    wins, no losses. `win_pct` is diluted to 0 (per the universal "draws
    don't count as wins" rule)."""
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(
        client,
        league_id,
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="5",
        pair2_score="5",
    )

    resp = await client.get(f"/leagues/{league_id}/standings")

    assert resp.status_code == 200
    standings = resp.json()["standings"]
    assert len(standings) == 2
    for row in standings:
        assert row["wins"] == 0
        assert row["losses"] == 0
        assert row["draws"] == 1
        assert row["matches_played"] == 1
        assert row["games_won"] == 5
        assert row["games_lost"] == 5


async def test_get_standings_multiple_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    # alice+bob win 2 matches, charlie+diana win 1
    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"), pair1_score="6", pair2_score="3")
    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"), pair1_score="7", pair2_score="5")
    await submit_match(client, league_id, pair1=("charlie", "diana"), pair2=("alice", "bob"), pair1_score="6", pair2_score="2")

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


async def test_get_standings_response_echoes_league_tie_breakers(
    client: AsyncClient,
) -> None:
    """The standings response includes the league's ordered ranking metrics
    so clients can label the displayed metric column ("Games won", "Games ±",
    ...) to match the league's primary tie_breaker. See design doc 17."""
    create_resp = await client.post(
        "/leagues",
        json={
            "title": "Games-Won League",
            "host_email": _DEFAULT_HOST_EMAIL,
            "rules": {
                "version": 8,
                "pair_matchup_idempotency": "once_per_league",
                "one_pair_per_player": True,
                "ranking_subject": "pair",
                "tie_breakers": ["games_won", "matches_won"],
            },
        },
    )
    assert create_resp.status_code == 201
    league_id = create_resp.json()["league_id"]

    resp = await client.get(f"/leagues/{league_id}/standings")

    assert resp.status_code == 200
    assert resp.json()["tie_breakers"] == ["games_won", "matches_won"]


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/standings/by-player
# ---------------------------------------------------------------------------


async def test_get_standings_by_player_returns_one_row_with_league_rank(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(
        client,
        league_id,
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    resp = await client.get(f"/leagues/{league_id}/standings/by-player?player_name=charlie")

    assert resp.status_code == 200
    standings = resp.json()["standings"]
    assert len(standings) == 1
    assert standings[0]["rank"] == 2
    assert standings[0]["wins"] == 0
    assert standings[0]["losses"] == 1
    assert set(
        [standings[0]["player1_nickname"], standings[0]["player2_nickname"]]
    ) == {"charlie", "diana"}


async def test_get_standings_by_player_matches_full_standings_for_winner(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(
        client,
        league_id,
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="6",
        pair2_score="3",
    )

    full = (await client.get(f"/leagues/{league_id}/standings")).json()["standings"]
    by_player = (
        await client.get(f"/leagues/{league_id}/standings/by-player?player_name=alice")
    ).json()["standings"]

    assert len(by_player) == 1
    winner_row = next(s for s in full if s["wins"] == 1)
    assert by_player[0] == winner_row


async def test_get_standings_by_player_player_not_found_returns_404(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id)

    resp = await client.get(f"/leagues/{league_id}/standings/by-player?player_name=ghost")

    assert resp.status_code == 404
    assert resp.json()["error"] == "PlayerNotFoundError"


async def test_get_standings_by_player_league_not_found_returns_404(
    client: AsyncClient,
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/standings/by-player?player_name=alice")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_get_standings_by_player_missing_param_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    resp = await client.get(f"/leagues/{league['league_id']}/standings/by-player")

    assert resp.status_code == 422


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
        pair1=("alice", "bob"),
        pair2=("charlie", "diana"),
        pair1_score="6",
        pair2_score="4",
    )

    resp = await client.get(f"/leagues/{league_id}/matches")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1

    record = matches[0]
    assert record["match_id"] == match["match_id"]
    assert record["pair1_score"] == "6"
    assert record["pair2_score"] == "4"
    assert set(
        [record["pair1_player1_nickname"], record["pair1_player2_nickname"]]
    ) == {"alice", "bob"}
    assert set(
        [record["pair2_player1_nickname"], record["pair2_player2_nickname"]]
    ) == {"charlie", "diana"}
    assert record["created_at"] is not None


async def test_get_match_history_multiple_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))
    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"), pair1_score="4", pair2_score="6")

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
    assert body["title"] == "Test League"
    assert body["players"] == []
    assert body["pairs"] == []
    assert body["latest_match_date"] is None
    # rules echoed so the frontend can fetch league title + rules in one trip.
    assert body["league_timezone"] == "America/Los_Angeles"
    assert body["rules"]["version"] == 8
    assert body["rules"]["pair_matchup_idempotency"] == "none"
    assert body["rules"]["one_pair_per_player"] is True
    assert body["rules"]["ranking_subject"] == "pair"
    assert body["rules"]["tie_breakers"] == ["matches_won"]
    assert body["rules"]["auto_register_players_on_match"] is True


async def test_get_league_roster_echoes_one_pair_per_player_false(client: AsyncClient) -> None:
    """When the league was created with `one_pair_per_player=false`, the
    roster response must surface the flag verbatim — the chat UI uses it
    to suppress the partner-conflict warning that only applies when each
    player can belong to a single pair."""
    league = await create_league(
        client,
        rules={
            "version": 8,
            "pair_matchup_idempotency": "none",
            "one_pair_per_player": False,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
        },
    )
    league_id = league["league_id"]

    resp = await client.get(f"/leagues/{league_id}/roster")

    assert resp.status_code == 200
    rules = resp.json()["rules"]
    assert rules["one_pair_per_player"] is False
    assert rules["ranking_subject"] == "pair"


async def test_get_league_roster_after_matches(client: AsyncClient) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"))

    resp = await client.get(f"/leagues/{league_id}/roster")

    assert resp.status_code == 200
    body = resp.json()

    assert body["title"] == "Test League"
    assert body["latest_match_date"] is not None
    assert len(body["players"]) == 4
    nicknames = {p["nickname"] for p in body["players"]}
    assert nicknames == {"alice", "bob", "charlie", "diana"}

    assert len(body["pairs"]) == 2
    for pair in body["pairs"]:
        assert "pair_id" in pair
        assert "player1_nickname" in pair
        assert "player2_nickname" in pair


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

    for pair in body["pairs"]:
        uuid.UUID(pair["pair_id"])


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/matches/by-player
# ---------------------------------------------------------------------------


async def test_get_match_history_by_player_returns_players_matches(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(
        client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"),
        pair1_score="6", pair2_score="4",
    )

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=alice")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    record = matches[0]
    assert record["match_id"] == match["match_id"]
    assert record["pair1_score"] == "6"
    assert record["pair2_score"] == "4"
    assert set([record["pair1_player1_nickname"], record["pair1_player2_nickname"]]) == {"alice", "bob"}
    assert set([record["pair2_player1_nickname"], record["pair2_player2_nickname"]]) == {"charlie", "diana"}
    assert record["created_at"] is not None


async def test_get_match_history_by_player_filters_out_other_matches(
    client: AsyncClient,
) -> None:
    """Matches not involving alice's pair must not appear in her history."""
    league = await create_league(client)
    league_id = league["league_id"]

    alice_match = await submit_match(
        client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana")
    )
    await submit_match(
        client, league_id, pair1=("edgar", "frank"), pair2=("george", "henry")
    )

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=alice")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["match_id"] == alice_match["match_id"]


async def test_get_match_history_by_player_returns_matches_as_pair2(
    client: AsyncClient,
) -> None:
    """alice+bob appearing as pair2 should still show up in alice's history."""
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(
        client, league_id, pair1=("charlie", "diana"), pair2=("alice", "bob"),
        pair1_score="3", pair2_score="6",
    )

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=alice")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["match_id"] == match["match_id"]


async def test_get_match_history_by_player_returns_all_matches(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana"), pair1_score="6", pair2_score="3")
    await submit_match(client, league_id, pair1=("charlie", "diana"), pair2=("alice", "bob"), pair1_score="4", pair2_score="6")

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=alice")

    assert resp.status_code == 200
    assert len(resp.json()["matches"]) == 2


async def test_get_match_history_by_player_case_insensitive(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    match = await submit_match(
        client, league_id, pair1=("alice", "bob"), pair2=("charlie", "diana")
    )

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=ALICE")

    assert resp.status_code == 200
    matches = resp.json()["matches"]
    assert len(matches) == 1
    assert matches[0]["match_id"] == match["match_id"]


async def test_get_match_history_by_player_player_not_found_returns_404(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    league_id = league["league_id"]

    await submit_match(client, league_id)

    resp = await client.get(f"/leagues/{league_id}/matches/by-player?player_name=ghost")

    assert resp.status_code == 404
    assert resp.json()["error"] == "PlayerNotFoundError"


async def test_get_match_history_by_player_league_not_found_returns_404(
    client: AsyncClient,
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/leagues/{fake_id}/matches/by-player?player_name=alice")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


async def test_get_match_history_by_player_missing_param_returns_422(
    client: AsyncClient,
) -> None:
    league = await create_league(client)
    resp = await client.get(f"/leagues/{league['league_id']}/matches/by-player")

    assert resp.status_code == 422
