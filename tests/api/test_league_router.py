"""Unit tests for the league router (player-facing endpoints).

All use cases are mocked; no database or infrastructure code is exercised.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.application.use_cases.create_league_use_case import CreateLeagueResult
from app.application.use_cases.get_league_roster_use_case import PlayerEntry, RosterView, TeamEntry
from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.application.use_cases.get_standings_use_case import GetStandingsUseCase
from app.application.use_cases.submit_match_result_use_case import SubmitMatchResultResult
from app.domain.exceptions import (
    DuplicateTeamPairMatchError,
    LeagueNotFoundError,
    LeagueTitleAlreadyExistsError,
    PlayerNotFoundError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
)
from app.domain.services.standings_calculator import StandingsEntry


# ---------------------------------------------------------------------------
# POST /leagues
# ---------------------------------------------------------------------------


class TestCreateLeague:
    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="league-uuid", host_token="host-token-value"
        )
        response = await client.post("/leagues", json={"title": "Summer League"})
        assert response.status_code == 201

    async def test_response_contains_league_id_and_host_token(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="abc-123", host_token="tok-xyz"
        )
        response = await client.post("/leagues", json={"title": "My League"})
        data = response.json()
        assert data["league_id"] == "abc-123"
        assert data["host_token"] == "tok-xyz"

    async def test_duplicate_title_returns_409(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.side_effect = LeagueTitleAlreadyExistsError("already exists")
        response = await client.post("/leagues", json={"title": "Summer League"})
        assert response.status_code == 409
        assert response.json()["error"] == "LeagueTitleAlreadyExistsError"

    async def test_blank_title_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/leagues", json={"title": ""})
        assert response.status_code == 422

    async def test_missing_title_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/leagues", json={})
        assert response.status_code == 422

    async def test_description_is_optional(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post("/leagues", json={"title": "L", "description": "desc"})
        assert response.status_code == 201


# ---------------------------------------------------------------------------
# POST /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


class TestSubmitMatchResult:
    _VALID_PAYLOAD = {
        "team1_nicknames": ["alice", "bob"],
        "team2_nicknames": ["charlie", "diana"],
        "team1_score": "6",
        "team2_score": "3",
    }

    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.return_value = SubmitMatchResultResult(match_id="match-uuid")
        response = await client.post("/leagues/league-id/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 201

    async def test_response_contains_match_id(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.return_value = SubmitMatchResultResult(match_id="m-123")
        response = await client.post("/leagues/league-id/matches", json=self._VALID_PAYLOAD)
        assert response.json()["match_id"] == "m-123"

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.post("/leagues/bad-id/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 404

    async def test_same_player_both_teams_returns_422(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = SamePlayerOnBothTeamsError("overlap")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 422

    async def test_same_player_within_team_returns_422(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = SamePlayerWithinSingleTeamError("dup")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 422

    async def test_team_conflict_returns_409(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = TeamConflictError("conflict")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 409

    async def test_duplicate_team_pair_returns_409(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = DuplicateTeamPairMatchError("dup")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 409
        assert response.json()["error"] == "DuplicateTeamPairMatchError"

    async def test_team1_with_one_nickname_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {**self._VALID_PAYLOAD, "team1_nicknames": ["alice"]}
        response = await client.post("/leagues/lid/matches", json=payload)
        assert response.status_code == 422

    async def test_team2_with_three_nicknames_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {**self._VALID_PAYLOAD, "team2_nicknames": ["a", "b", "c"]}
        response = await client.post("/leagues/lid/matches", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/standings
# ---------------------------------------------------------------------------


class TestGetStandings:
    async def test_returns_200_with_standings_list(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = [
            StandingsEntry(
                team_id="t1", player1_nickname="alice", player2_nickname="bob",
                wins=2, losses=1, rank=1,
            )
        ]
        response = await client.get("/leagues/lid/standings")
        assert response.status_code == 200
        data = response.json()
        assert len(data["standings"]) == 1
        assert data["standings"][0]["rank"] == 1
        assert data["standings"][0]["wins"] == 2

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/standings")
        assert response.status_code == 404

    async def test_empty_standings_returned_as_empty_list(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = []
        response = await client.get("/leagues/lid/standings")
        assert response.status_code == 200
        assert response.json()["standings"] == []


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/standings/by-player
# ---------------------------------------------------------------------------


class TestGetStandingsByPlayer:
    async def test_returns_200_with_standings_list(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = [
            StandingsEntry(
                team_id="t1",
                player1_nickname="alice",
                player2_nickname="bob",
                wins=2,
                losses=1,
                rank=1,
            )
        ]
        response = await client.get("/leagues/lid/standings/by-player?player_name=alice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["standings"]) == 1
        assert data["standings"][0]["rank"] == 1
        assert data["standings"][0]["wins"] == 2

    async def test_passes_params_to_use_case(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = []
        await client.get("/leagues/lid/standings/by-player?player_name=alice")
        call_args = mock_get_standings_by_player_uc.execute.call_args[0][0]
        assert call_args.player_name == "alice"
        assert call_args.league_id == "lid"

    async def test_missing_player_name_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/leagues/lid/standings/by-player")
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/standings/by-player?player_name=alice")
        assert response.status_code == 404

    async def test_player_not_found_returns_404(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.side_effect = PlayerNotFoundError("not found")
        response = await client.get("/leagues/lid/standings/by-player?player_name=ghost")
        assert response.status_code == 404
        assert response.json()["error"] == "PlayerNotFoundError"

    async def test_empty_result_returns_empty_standings_list(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = []
        response = await client.get("/leagues/lid/standings/by-player?player_name=alice")
        assert response.status_code == 200
        assert response.json()["standings"] == []


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


class TestGetMatchHistory:
    async def test_returns_200_with_matches_list(
        self, client: AsyncClient, mock_get_match_history_uc: AsyncMock
    ) -> None:
        mock_get_match_history_uc.execute.return_value = [
            MatchHistoryRecord(
                match_id="m1",
                team1_player1_nickname="alice",
                team1_player2_nickname="bob",
                team2_player1_nickname="charlie",
                team2_player2_nickname="diana",
                team1_score="6",
                team2_score="3",
                created_at=datetime(2025, 1, 1),
            )
        ]
        response = await client.get("/leagues/lid/matches")
        assert response.status_code == 200
        data = response.json()
        assert len(data["matches"]) == 1
        assert data["matches"][0]["match_id"] == "m1"

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_match_history_uc: AsyncMock
    ) -> None:
        mock_get_match_history_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/matches")
        assert response.status_code == 404

    async def test_empty_match_history_returned_as_empty_list(
        self, client: AsyncClient, mock_get_match_history_uc: AsyncMock
    ) -> None:
        mock_get_match_history_uc.execute.return_value = []
        response = await client.get("/leagues/lid/matches")
        assert response.status_code == 200
        assert response.json()["matches"] == []


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/roster
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/matches/by-player
# ---------------------------------------------------------------------------


class TestGetMatchHistoryByPlayer:
    _MATCH_RECORD = MatchHistoryRecord(
        match_id="m1",
        team1_player1_nickname="alice",
        team1_player2_nickname="bob",
        team2_player1_nickname="charlie",
        team2_player2_nickname="diana",
        team1_score="6",
        team2_score="3",
        created_at=datetime(2025, 1, 1),
    )

    async def test_returns_200_with_matches_list(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.return_value = [self._MATCH_RECORD]
        response = await client.get("/leagues/lid/matches/by-player?player_name=alice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["matches"]) == 1
        assert data["matches"][0]["match_id"] == "m1"

    async def test_passes_player_name_to_use_case(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.return_value = []
        await client.get("/leagues/lid/matches/by-player?player_name=alice")
        call_args = mock_get_match_history_by_player_uc.execute.call_args[0][0]
        assert call_args.player_name == "alice"
        assert call_args.league_id == "lid"

    async def test_missing_player_name_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/leagues/lid/matches/by-player")
        assert response.status_code == 422

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/matches/by-player?player_name=alice")
        assert response.status_code == 404

    async def test_player_not_found_returns_404(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.side_effect = PlayerNotFoundError("not found")
        response = await client.get("/leagues/lid/matches/by-player?player_name=ghost")
        assert response.status_code == 404
        assert response.json()["error"] == "PlayerNotFoundError"

    async def test_empty_result_returns_empty_matches_list(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.return_value = []
        response = await client.get("/leagues/lid/matches/by-player?player_name=alice")
        assert response.status_code == 200
        assert response.json()["matches"] == []


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/roster
# ---------------------------------------------------------------------------


class TestGetLeagueRoster:
    async def test_returns_200_with_players_and_teams(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.return_value = RosterView(
            players=[PlayerEntry(player_id="p1", nickname="alice")],
            teams=[TeamEntry(team_id="t1", player1_nickname="alice", player2_nickname="bob")],
        )
        response = await client.get("/leagues/lid/roster")
        assert response.status_code == 200
        data = response.json()
        assert len(data["players"]) == 1
        assert data["players"][0]["nickname"] == "alice"
        assert len(data["teams"]) == 1

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/roster")
        assert response.status_code == 404

    async def test_empty_roster_returns_empty_lists(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.return_value = RosterView(players=[], teams=[])
        response = await client.get("/leagues/lid/roster")
        assert response.status_code == 200
        data = response.json()
        assert data["players"] == []
        assert data["teams"] == []
