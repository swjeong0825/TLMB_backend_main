"""E2E tests for the player-facing `PATCH /leagues/{id}/matches/{id}` endpoint.

The route lives on the player router and has no `X-Host-Token` requirement.
The gate is purely time-based: edits are allowed only while the match's
`created_at` is within the configured window
(`PLAYER_SCORE_EDIT_WINDOW_SECONDS`, default 3600). Outside the window,
the request 422s with `MatchEditWindowExpiredError`.

Admins still hit the legacy `PATCH /admin/leagues/{id}/matches/{id}`
endpoint (verified in `test_admin_api.py`) — its tests must continue
to pass unchanged.

To exercise the expired-window branch deterministically we use the
`PLAYER_SCORE_EDIT_WINDOW_SECONDS=0` env override + the `get_edit_match_score_use_case`
FastAPI dependency override. We don't mock `datetime.now` so the rest of
the system stays honest.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.application.use_cases.edit_match_score_use_case import EditMatchScoreUseCase
from app.dependencies import (
    get_edit_match_score_use_case,
    get_league_repo,
    get_match_repo,
)
from app.main import app


_DEFAULT_HOST_EMAIL = "glhf0825@gmail.com"


async def _create_league(client: AsyncClient) -> dict:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Player Edit Test League",
            "host_email": _DEFAULT_HOST_EMAIL,
            # Default rules already work; we don't need
            # match_pair_idempotency loose here because we never re-submit.
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _submit_match(client: AsyncClient, league_id: str) -> dict:
    resp = await client.post(
        f"/leagues/{league_id}/matches",
        json={
            "team1_nicknames": ["alice", "bob"],
            "team2_nicknames": ["charlie", "diana"],
            "team1_score": "6",
            "team2_score": "3",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Happy path: fresh match, no host token, score is updated
# ---------------------------------------------------------------------------


async def test_player_edit_inside_default_window_succeeds(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]
    # The submit response now carries the server-authoritative created_at.
    assert "created_at" in match and match["created_at"]

    resp = await client.patch(
        f"/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "7", "team2_score": "5"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["match_id"] == match_id
    assert body["team1_score"] == "7"
    assert body["team2_score"] == "5"


async def test_player_edit_persists_to_history(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]

    await client.patch(
        f"/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "2", "team2_score": "6"},
    )

    history = (await client.get(f"/leagues/{league_id}/matches")).json()["matches"]
    updated = next(m for m in history if m["match_id"] == match_id)
    assert updated["team1_score"] == "2"
    assert updated["team2_score"] == "6"


# ---------------------------------------------------------------------------
# Window expired: shrink the window to 0 via the FastAPI dep, force 422
# ---------------------------------------------------------------------------


@pytest.fixture
def zero_window_override():
    """Override the edit-match-score use case to have a 0-second window.

    Using `app.dependency_overrides` (rather than monkeypatching the env
    var) avoids re-importing modules and works while the test app is
    already alive.
    """
    from fastapi import Depends

    def _override(
        league_repo=Depends(get_league_repo),
        match_repo=Depends(get_match_repo),
    ) -> EditMatchScoreUseCase:
        return EditMatchScoreUseCase(league_repo, match_repo, window_seconds=0)

    app.dependency_overrides[get_edit_match_score_use_case] = _override
    yield
    app.dependency_overrides.pop(get_edit_match_score_use_case, None)


async def test_player_edit_outside_window_returns_422(
    client: AsyncClient, zero_window_override
) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]

    resp = await client.patch(
        f"/leagues/{league_id}/matches/{match_id}",
        json={"team1_score": "7", "team2_score": "5"},
    )

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "MatchEditWindowExpiredError"
    assert body["match_id"] == match_id
    assert body["window_seconds"] == 0
    assert body["age_seconds"] >= 0


# ---------------------------------------------------------------------------
# Validation / not-found paths reuse the same handlers
# ---------------------------------------------------------------------------


async def test_player_edit_invalid_score_returns_422(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    resp = await client.patch(
        f"/leagues/{league_id}/matches/{match['match_id']}",
        json={"team1_score": "abc", "team2_score": "5"},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "InvalidSetScoreError"


async def test_player_edit_match_not_found_returns_404(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.patch(
        f"/leagues/{league_id}/matches/{fake_match_id}",
        json={"team1_score": "6", "team2_score": "3"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "MatchNotFoundError"


async def test_player_edit_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_league_id = "00000000-0000-0000-0000-000000000000"
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.patch(
        f"/leagues/{fake_league_id}/matches/{fake_match_id}",
        json={"team1_score": "6", "team2_score": "3"},
    )

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# Roster endpoint surfaces the configured window
# ---------------------------------------------------------------------------


async def test_roster_response_includes_player_score_edit_window_seconds(
    client: AsyncClient,
) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    body = (await client.get(f"/leagues/{league_id}/roster")).json()
    assert "player_score_edit_window_seconds" in body
    assert isinstance(body["player_score_edit_window_seconds"], int)
    assert body["player_score_edit_window_seconds"] >= 0
