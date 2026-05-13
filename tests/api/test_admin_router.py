"""Unit tests for the admin router (host-only endpoints).

All use cases are mocked; no database or infrastructure code is exercised.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.application.use_cases.add_allowlist_entries_use_case import (
    AddAllowlistEntriesResult,
    AllowlistEntry,
)
from app.application.use_cases.edit_match_score_use_case import UpdatedMatchResult
from app.application.use_cases.edit_player_nickname_use_case import UpdatedPlayerResult
from app.domain.exceptions import (
    AllowlistEntryNotFoundError,
    AllowlistNicknameAlreadyExistsError,
    LeagueNotFoundError,
    MatchNotFoundError,
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)


# ---------------------------------------------------------------------------
# PATCH /admin/leagues/{league_id}/players/{player_id}
# ---------------------------------------------------------------------------


class TestEditPlayerNickname:
    _URL = "/admin/leagues/league-id/players/player-id"

    async def test_returns_200_on_success(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.return_value = UpdatedPlayerResult(
            player_id="player-id", new_nickname="alicia"
        )
        response = await client.patch(
            self._URL,
            json={"new_nickname": "alicia"},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 200

    async def test_response_contains_updated_fields(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.return_value = UpdatedPlayerResult(
            player_id="pid-123", new_nickname="newname"
        )
        response = await client.patch(
            self._URL,
            json={"new_nickname": "newname"},
            headers={"X-Host-Token": "valid-token"},
        )
        data = response.json()
        assert data["player_id"] == "pid-123"
        assert data["new_nickname"] == "newname"

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(self._URL, json={"new_nickname": "newname"})
        assert response.status_code == 422

    async def test_blank_nickname_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(
            self._URL,
            json={"new_nickname": ""},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.patch(
            self._URL,
            json={"new_nickname": "alicia"},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_player_not_found_returns_404(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.side_effect = PlayerNotFoundError("not found")
        response = await client.patch(
            self._URL,
            json={"new_nickname": "alicia"},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.patch(
            self._URL,
            json={"new_nickname": "alicia"},
            headers={"X-Host-Token": "wrong-token"},
        )
        assert response.status_code == 401

    async def test_duplicate_nickname_returns_409(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.side_effect = NicknameAlreadyInUseError("taken")
        response = await client.patch(
            self._URL,
            json={"new_nickname": "bob"},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 409


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/teams/{team_id}
# ---------------------------------------------------------------------------


class TestDeleteTeam:
    _URL = "/admin/leagues/league-id/teams/team-id"

    async def test_returns_204_on_success(
        self, client: AsyncClient, mock_delete_team_uc: AsyncMock
    ) -> None:
        mock_delete_team_uc.execute.return_value = None
        response = await client.delete(
            self._URL, headers={"X-Host-Token": "valid-token"}
        )
        assert response.status_code == 204

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete(self._URL)
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_delete_team_uc: AsyncMock
    ) -> None:
        mock_delete_team_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_team_not_found_returns_404(
        self, client: AsyncClient, mock_delete_team_uc: AsyncMock
    ) -> None:
        mock_delete_team_uc.execute.side_effect = TeamNotFoundError("not found")
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_delete_team_uc: AsyncMock
    ) -> None:
        mock_delete_team_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.delete(self._URL, headers={"X-Host-Token": "wrong"})
        assert response.status_code == 401

    async def test_team_with_matches_returns_409(
        self, client: AsyncClient, mock_delete_team_uc: AsyncMock
    ) -> None:
        mock_delete_team_uc.execute.side_effect = TeamHasMatchesError("has matches")
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 409
        assert response.json()["error"] == "TeamHasMatchesError"


# ---------------------------------------------------------------------------
# PATCH /admin/leagues/{league_id}/matches/{match_id}
# ---------------------------------------------------------------------------


class TestEditMatchScore:
    _URL = "/admin/leagues/league-id/matches/match-id"

    async def test_returns_200_on_success(
        self, client: AsyncClient, mock_edit_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_match_score_uc.execute.return_value = UpdatedMatchResult(
            match_id="match-id", team1_score="4", team2_score="6"
        )
        response = await client.patch(
            self._URL,
            json={"team1_score": "4", "team2_score": "6"},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 200

    async def test_response_contains_updated_scores(
        self, client: AsyncClient, mock_edit_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_match_score_uc.execute.return_value = UpdatedMatchResult(
            match_id="mid", team1_score="7", team2_score="5"
        )
        response = await client.patch(
            self._URL,
            json={"team1_score": "7", "team2_score": "5"},
            headers={"X-Host-Token": "token"},
        )
        data = response.json()
        assert data["team1_score"] == "7"
        assert data["team2_score"] == "5"
        assert data["match_id"] == "mid"

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(
            self._URL, json={"team1_score": "6", "team2_score": "3"}
        )
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_edit_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_match_score_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.patch(
            self._URL,
            json={"team1_score": "6", "team2_score": "3"},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_match_not_found_returns_404(
        self, client: AsyncClient, mock_edit_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_match_score_uc.execute.side_effect = MatchNotFoundError("not found")
        response = await client.patch(
            self._URL,
            json={"team1_score": "6", "team2_score": "3"},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_edit_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_match_score_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.patch(
            self._URL,
            json={"team1_score": "6", "team2_score": "3"},
            headers={"X-Host-Token": "wrong"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/matches/{match_id}
# ---------------------------------------------------------------------------


class TestDeleteMatch:
    _URL = "/admin/leagues/league-id/matches/match-id"

    async def test_returns_204_on_success(
        self, client: AsyncClient, mock_delete_match_uc: AsyncMock
    ) -> None:
        mock_delete_match_uc.execute.return_value = None
        response = await client.delete(
            self._URL, headers={"X-Host-Token": "valid-token"}
        )
        assert response.status_code == 204

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete(self._URL)
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_delete_match_uc: AsyncMock
    ) -> None:
        mock_delete_match_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_match_not_found_returns_404(
        self, client: AsyncClient, mock_delete_match_uc: AsyncMock
    ) -> None:
        mock_delete_match_uc.execute.side_effect = MatchNotFoundError("not found")
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_delete_match_uc: AsyncMock
    ) -> None:
        mock_delete_match_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.delete(self._URL, headers={"X-Host-Token": "wrong"})
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /admin/leagues/{league_id}/allowlist
# ---------------------------------------------------------------------------


class TestAddAllowlistEntries:
    _URL = "/admin/leagues/league-id/allowlist"

    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_add_allowlist_entries_uc: AsyncMock
    ) -> None:
        mock_add_allowlist_entries_uc.execute.return_value = AddAllowlistEntriesResult(
            allowlist=[
                AllowlistEntry(allowlist_entry_id="ae-1", nickname="alex"),
            ]
        )
        response = await client.post(
            self._URL,
            json={"nicknames": ["Alex"]},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 201

    async def test_response_contains_added_entries(
        self, client: AsyncClient, mock_add_allowlist_entries_uc: AsyncMock
    ) -> None:
        mock_add_allowlist_entries_uc.execute.return_value = AddAllowlistEntriesResult(
            allowlist=[
                AllowlistEntry(allowlist_entry_id="ae-1", nickname="alex"),
                AllowlistEntry(allowlist_entry_id="ae-2", nickname="daniel"),
            ]
        )
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex", "daniel"]},
            headers={"X-Host-Token": "token"},
        )
        data = response.json()
        assert len(data["allowlist"]) == 2
        assert data["allowlist"][0]["allowlist_entry_id"] == "ae-1"
        assert data["allowlist"][0]["nickname"] == "alex"

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(self._URL, json={"nicknames": ["alex"]})
        assert response.status_code == 422

    async def test_empty_nicknames_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            self._URL,
            json={"nicknames": []},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_blank_entry_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex", "  "]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_add_allowlist_entries_uc: AsyncMock
    ) -> None:
        mock_add_allowlist_entries_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_add_allowlist_entries_uc: AsyncMock
    ) -> None:
        mock_add_allowlist_entries_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "wrong"},
        )
        assert response.status_code == 401

    async def test_duplicate_returns_409(
        self, client: AsyncClient, mock_add_allowlist_entries_uc: AsyncMock
    ) -> None:
        mock_add_allowlist_entries_uc.execute.side_effect = (
            AllowlistNicknameAlreadyExistsError("already")
        )
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "AllowlistNicknameAlreadyExistsError"


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/allowlist/{allowlist_entry_id}
# ---------------------------------------------------------------------------


class TestRemoveAllowlistEntry:
    _URL = "/admin/leagues/league-id/allowlist/ae-id"

    async def test_returns_204_on_success(
        self, client: AsyncClient, mock_remove_allowlist_entry_uc: AsyncMock
    ) -> None:
        mock_remove_allowlist_entry_uc.execute.return_value = None
        response = await client.delete(
            self._URL, headers={"X-Host-Token": "valid-token"}
        )
        assert response.status_code == 204

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete(self._URL)
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_remove_allowlist_entry_uc: AsyncMock
    ) -> None:
        mock_remove_allowlist_entry_uc.execute.side_effect = LeagueNotFoundError(
            "not found"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_allowlist_entry_not_found_returns_404(
        self, client: AsyncClient, mock_remove_allowlist_entry_uc: AsyncMock
    ) -> None:
        mock_remove_allowlist_entry_uc.execute.side_effect = AllowlistEntryNotFoundError(
            "not found"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404
        assert response.json()["error"] == "AllowlistEntryNotFoundError"

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_remove_allowlist_entry_uc: AsyncMock
    ) -> None:
        mock_remove_allowlist_entry_uc.execute.side_effect = UnauthorizedError(
            "unauthorized"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "wrong"})
        assert response.status_code == 401
