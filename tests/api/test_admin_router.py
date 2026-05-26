"""Unit tests for the admin router (host-only endpoints).

All use cases are mocked; no database or infrastructure code is exercised.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.application.use_cases.add_players_use_case import (
    AddPlayersResult,
    PlayerEntry,
)
from app.application.use_cases.edit_match_score_use_case import UpdatedMatchResult
from app.application.use_cases.edit_player_nickname_use_case import UpdatedPlayerResult
from app.application.use_cases.get_league_admin_info_use_case import LeagueAdminInfoView
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchNotFoundError,
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)


# ---------------------------------------------------------------------------
# GET /admin/leagues/{league_id}
# ---------------------------------------------------------------------------


class TestGetLeagueAdminInfo:
    _URL = "/admin/leagues/league-id"

    async def test_returns_200_with_host_email(
        self, client: AsyncClient, mock_get_league_admin_info_uc: AsyncMock
    ) -> None:
        mock_get_league_admin_info_uc.execute.return_value = LeagueAdminInfoView(
            host_email="host@example.com"
        )
        response = await client.get(
            self._URL,
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 200
        assert response.json() == {"host_email": "host@example.com"}

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.get(self._URL)
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_league_admin_info_uc: AsyncMock
    ) -> None:
        mock_get_league_admin_info_uc.execute.side_effect = LeagueNotFoundError("missing")
        response = await client.get(
            self._URL,
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 404

    async def test_invalid_host_token_returns_401(
        self, client: AsyncClient, mock_get_league_admin_info_uc: AsyncMock
    ) -> None:
        mock_get_league_admin_info_uc.execute.side_effect = UnauthorizedError("bad token")
        response = await client.get(
            self._URL,
            headers={"X-Host-Token": "wrong-token"},
        )
        assert response.status_code == 401


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
            player_id="pid-123", new_nickname="newname", rating=3.5
        )
        response = await client.patch(
            self._URL,
            json={"new_nickname": "newname"},
            headers={"X-Host-Token": "valid-token"},
        )
        data = response.json()
        assert data["player_id"] == "pid-123"
        assert data["new_nickname"] == "newname"
        assert data["rating"] == 3.5

    async def test_rating_only_update_is_allowed(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.return_value = UpdatedPlayerResult(
            player_id="pid-123", new_nickname="alice", rating=3.5
        )
        response = await client.patch(
            self._URL,
            json={"rating": 3.5},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 200
        command = mock_edit_player_nickname_uc.execute.await_args.args[0]
        assert command.new_nickname is None
        assert command.rating == 3.5
        assert command.rating_supplied is True

    async def test_rating_null_clears_rating(
        self, client: AsyncClient, mock_edit_player_nickname_uc: AsyncMock
    ) -> None:
        mock_edit_player_nickname_uc.execute.return_value = UpdatedPlayerResult(
            player_id="pid-123", new_nickname="alice", rating=None
        )
        response = await client.patch(
            self._URL,
            json={"rating": None},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 200
        command = mock_edit_player_nickname_uc.execute.await_args.args[0]
        assert command.rating is None
        assert command.rating_supplied is True

    async def test_empty_patch_body_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(
            self._URL,
            json={},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_null_nickname_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(
            self._URL,
            json={"new_nickname": None},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_negative_rating_returns_422(self, client: AsyncClient) -> None:
        response = await client.patch(
            self._URL,
            json={"rating": -1},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

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
# POST /admin/leagues/{league_id}/players
# ---------------------------------------------------------------------------


class TestAddPlayers:
    _URL = "/admin/leagues/league-id/players"

    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_add_players_uc: AsyncMock
    ) -> None:
        mock_add_players_uc.execute.return_value = AddPlayersResult(
            players=[
                PlayerEntry(player_id="p-1", nickname="alex", rating=3.5),
            ]
        )
        response = await client.post(
            self._URL,
            json={"players": [{"nickname": "Alex", "rating": 3.5}]},
            headers={"X-Host-Token": "valid-token"},
        )
        assert response.status_code == 201
        command = mock_add_players_uc.execute.await_args.args[0]
        assert command.nicknames == ["Alex"]
        assert command.ratings == [3.5]

    async def test_response_contains_added_players(
        self, client: AsyncClient, mock_add_players_uc: AsyncMock
    ) -> None:
        mock_add_players_uc.execute.return_value = AddPlayersResult(
            players=[
                PlayerEntry(player_id="p-1", nickname="alex"),
                PlayerEntry(player_id="p-2", nickname="daniel"),
            ]
        )
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex", "daniel"]},
            headers={"X-Host-Token": "token"},
        )
        data = response.json()
        assert len(data["players"]) == 2
        assert data["players"][0]["player_id"] == "p-1"
        assert data["players"][0]["nickname"] == "alex"
        assert data["players"][0]["rating"] is None

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

    async def test_players_shape_blank_nickname_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            self._URL,
            json={"players": [{"nickname": "  ", "rating": 3.5}]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_players_shape_negative_rating_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            self._URL,
            json={"players": [{"nickname": "alex", "rating": -1}]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_cannot_mix_nicknames_and_players_shapes(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            self._URL,
            json={
                "nicknames": ["alex"],
                "players": [{"nickname": "daniel", "rating": 3.5}],
            },
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_add_players_uc: AsyncMock
    ) -> None:
        mock_add_players_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 404

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_add_players_uc: AsyncMock
    ) -> None:
        mock_add_players_uc.execute.side_effect = UnauthorizedError("unauthorized")
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "wrong"},
        )
        assert response.status_code == 401

    async def test_duplicate_returns_409(
        self, client: AsyncClient, mock_add_players_uc: AsyncMock
    ) -> None:
        mock_add_players_uc.execute.side_effect = NicknameAlreadyInUseError("already")
        response = await client.post(
            self._URL,
            json={"nicknames": ["alex"]},
            headers={"X-Host-Token": "token"},
        )
        assert response.status_code == 409
        assert response.json()["error"] == "NicknameAlreadyInUseError"


# ---------------------------------------------------------------------------
# DELETE /admin/leagues/{league_id}/players/{player_id}
# ---------------------------------------------------------------------------


class TestRemovePlayerFromRoster:
    _URL = "/admin/leagues/league-id/players/player-id"

    async def test_returns_204_on_success(
        self, client: AsyncClient, mock_remove_player_from_roster_uc: AsyncMock
    ) -> None:
        mock_remove_player_from_roster_uc.execute.return_value = None
        response = await client.delete(
            self._URL, headers={"X-Host-Token": "valid-token"}
        )
        assert response.status_code == 204

    async def test_missing_host_token_returns_422(self, client: AsyncClient) -> None:
        response = await client.delete(self._URL)
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_remove_player_from_roster_uc: AsyncMock
    ) -> None:
        mock_remove_player_from_roster_uc.execute.side_effect = LeagueNotFoundError(
            "not found"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404

    async def test_player_not_found_returns_404(
        self, client: AsyncClient, mock_remove_player_from_roster_uc: AsyncMock
    ) -> None:
        mock_remove_player_from_roster_uc.execute.side_effect = PlayerNotFoundError(
            "not found"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 404
        assert response.json()["error"] == "PlayerNotFoundError"

    async def test_wrong_token_returns_401(
        self, client: AsyncClient, mock_remove_player_from_roster_uc: AsyncMock
    ) -> None:
        mock_remove_player_from_roster_uc.execute.side_effect = UnauthorizedError(
            "unauthorized"
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "wrong"})
        assert response.status_code == 401

    async def test_player_with_participation_returns_409_with_counts(
        self, client: AsyncClient, mock_remove_player_from_roster_uc: AsyncMock
    ) -> None:
        """Removing a player with non-zero team/match participation is
        rejected with 409. The structured `teams_count` and `matches_count`
        fields are surfaced verbatim so the chat agent and frontend can
        render a clear "X teams, Y matches" message."""
        mock_remove_player_from_roster_uc.execute.side_effect = (
            PlayerHasParticipationError(
                "Player 'pid' has 1 team(s) and 3 match(es); only players with zero participation can be removed",
                player_id="player-id",
                teams_count=1,
                matches_count=3,
            )
        )
        response = await client.delete(self._URL, headers={"X-Host-Token": "token"})
        assert response.status_code == 409
        body = response.json()
        assert body["error"] == "PlayerHasParticipationError"
        assert body["player_id"] == "player-id"
        assert body["teams_count"] == 1
        assert body["matches_count"] == 3
