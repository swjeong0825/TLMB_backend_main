"""E2E tests for the player-facing `DELETE /leagues/{id}/matches/{id}` endpoint.

Mirrors `test_player_edit_match.py`: the route lives on the player
router and has no `X-Host-Token` requirement. The gate is purely
time-based: deletes are allowed only while the match's `created_at`
is within the configured window
(`PLAYER_MATCH_DELETE_WINDOW_SECONDS`, default 600s). Outside the
window the request 422s with `MatchDeleteWindowExpiredError`.

Admins still hit the legacy `DELETE /admin/leagues/{id}/matches/{id}`
endpoint (verified in `test_admin_api.py`) — its tests must continue
to pass unchanged.

To exercise the expired-window branch deterministically we use the
`get_delete_match_use_case` FastAPI dependency override with
`window_seconds=0`, rather than mocking `datetime.now`.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.application.use_cases.delete_match_use_case import DeleteMatchUseCase
from app.dependencies import (
    get_delete_match_use_case,
    get_league_repo,
    get_match_repo,
)
from app.main import app


_DEFAULT_HOST_EMAIL = "glhf0825@gmail.com"


async def _create_league(client: AsyncClient) -> dict:
    resp = await client.post(
        "/leagues",
        json={
            "title": "Player Delete Test League",
            "host_email": _DEFAULT_HOST_EMAIL,
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
# Happy path: fresh match, no host token, match is deleted
# ---------------------------------------------------------------------------


async def test_player_delete_inside_default_window_succeeds(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]
    assert "created_at" in match and match["created_at"]

    resp = await client.delete(f"/leagues/{league_id}/matches/{match_id}")

    assert resp.status_code == 204, resp.text


async def test_player_delete_removes_from_history(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]

    await client.delete(f"/leagues/{league_id}/matches/{match_id}")

    history = (await client.get(f"/leagues/{league_id}/matches")).json()["matches"]
    assert all(m["match_id"] != match_id for m in history)


# ---------------------------------------------------------------------------
# Window expired: shrink the window to 0 via the FastAPI dep, force 422
# ---------------------------------------------------------------------------


@pytest.fixture
def zero_delete_window_override():
    """Override the delete-match use case to have a 0-second window.

    Using `app.dependency_overrides` (rather than monkeypatching the env
    var) avoids re-importing modules and works while the test app is
    already alive.
    """
    from fastapi import Depends

    def _override(
        league_repo=Depends(get_league_repo),
        match_repo=Depends(get_match_repo),
    ) -> DeleteMatchUseCase:
        return DeleteMatchUseCase(league_repo, match_repo, window_seconds=0)

    app.dependency_overrides[get_delete_match_use_case] = _override
    yield
    app.dependency_overrides.pop(get_delete_match_use_case, None)


async def test_player_delete_outside_window_returns_422(
    client: AsyncClient, zero_delete_window_override
) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]

    resp = await client.delete(f"/leagues/{league_id}/matches/{match_id}")

    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "MatchDeleteWindowExpiredError"
    assert body["match_id"] == match_id
    assert body["window_seconds"] == 0
    assert body["age_seconds"] >= 0


async def test_player_delete_outside_window_does_not_remove_match(
    client: AsyncClient, zero_delete_window_override
) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    match = await _submit_match(client, league_id)
    match_id = match["match_id"]

    await client.delete(f"/leagues/{league_id}/matches/{match_id}")

    history = (await client.get(f"/leagues/{league_id}/matches")).json()["matches"]
    assert any(m["match_id"] == match_id for m in history)


# ---------------------------------------------------------------------------
# Not-found paths reuse the same handlers
# ---------------------------------------------------------------------------


async def test_player_delete_match_not_found_returns_404(client: AsyncClient) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(f"/leagues/{league_id}/matches/{fake_match_id}")

    assert resp.status_code == 404
    assert resp.json()["error"] == "MatchNotFoundError"


async def test_player_delete_league_not_found_returns_404(client: AsyncClient) -> None:
    fake_league_id = "00000000-0000-0000-0000-000000000000"
    fake_match_id = "00000000-0000-0000-0000-000000000001"

    resp = await client.delete(f"/leagues/{fake_league_id}/matches/{fake_match_id}")

    assert resp.status_code == 404
    assert resp.json()["error"] == "LeagueNotFoundError"


# ---------------------------------------------------------------------------
# Roster endpoint surfaces the configured delete window
# ---------------------------------------------------------------------------


async def test_roster_response_includes_player_match_delete_window_seconds(
    client: AsyncClient,
) -> None:
    league = await _create_league(client)
    league_id = league["league_id"]

    body = (await client.get(f"/leagues/{league_id}/roster")).json()
    assert "player_match_delete_window_seconds" in body
    assert isinstance(body["player_match_delete_window_seconds"], int)
    assert body["player_match_delete_window_seconds"] >= 0
