"""Unit tests for the league router (player-facing endpoints).

All use cases are mocked; no database or infrastructure code is exercised.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.application.use_cases.create_league_use_case import CreateLeagueResult
from app.application.use_cases.search_leagues_by_title_prefix_use_case import LeagueListItem
from app.application.use_cases.get_league_roster_use_case import PlayerEntry, RosterView, PairEntry
from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.application.use_cases.get_standings_use_case import GetStandingsUseCase, StandingsView
from app.application.use_cases.submit_match_result_use_case import SubmitMatchResultResult
from app.application.use_cases.submit_singles_match_result_use_case import (
    SubmitSinglesMatchResultResult,
)
from app.application.use_cases.edit_singles_match_score_use_case import (
    UpdatedSinglesMatchResult,
)
from app.domain.exceptions import (
    DuplicatePairMatchupMatchError,
    LeagueNotFoundError,
    LeagueTitleAlreadyExistsError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothSidesError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
    PairConflictError,
)
from app.domain.services.standings_calculator import StandingsEntry


# ---------------------------------------------------------------------------
# POST /leagues
# ---------------------------------------------------------------------------


_HOST_EMAIL = "host@example.com"


def _create_league_body(**overrides: object) -> dict:
    """Return a minimal valid POST /leagues body, with `host_email` set so
    individual tests don't have to repeat it. Override per-test as needed.
    """
    body: dict = {"title": "Summer League", "host_email": _HOST_EMAIL}
    body.update(overrides)
    return body


class TestCreateLeague:
    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="league-uuid", host_token="host-token-value"
        )
        response = await client.post("/leagues", json=_create_league_body())
        assert response.status_code == 201

    async def test_response_contains_league_id_and_host_token(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="abc-123", host_token="tok-xyz"
        )
        response = await client.post("/leagues", json=_create_league_body(title="My League"))
        data = response.json()
        assert data["league_id"] == "abc-123"
        assert data["host_token"] == "tok-xyz"
        assert "host_email" not in data  # private: never echoed on read

    async def test_duplicate_title_returns_409(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.side_effect = LeagueTitleAlreadyExistsError("already exists")
        response = await client.post("/leagues", json=_create_league_body())
        assert response.status_code == 409
        assert response.json()["error"] == "LeagueTitleAlreadyExistsError"

    async def test_blank_title_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/leagues", json=_create_league_body(title=""))
        assert response.status_code == 422

    async def test_missing_title_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/leagues", json={"host_email": _HOST_EMAIL})
        assert response.status_code == 422

    async def test_missing_host_email_returns_422(self, client: AsyncClient) -> None:
        response = await client.post("/leagues", json={"title": "No Email"})
        assert response.status_code == 422

    async def test_malformed_host_email_returns_422(self, client: AsyncClient) -> None:
        response = await client.post(
            "/leagues", json=_create_league_body(host_email="not-an-email")
        )
        assert response.status_code == 422

    async def test_host_email_is_forwarded_to_use_case(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post(
            "/leagues", json=_create_league_body(host_email="host@example.com")
        )
        assert response.status_code == 201
        cmd = mock_create_league_uc.execute.call_args[0][0]
        assert cmd.host_email == "host@example.com"

    async def test_league_timezone_is_forwarded_to_use_case(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post(
            "/leagues",
            json=_create_league_body(league_timezone="Asia/Seoul"),
        )
        assert response.status_code == 201
        cmd = mock_create_league_uc.execute.call_args[0][0]
        assert cmd.league_timezone == "Asia/Seoul"

    async def test_description_is_optional(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post(
            "/leagues", json=_create_league_body(title="L", description="desc")
        )
        assert response.status_code == 201

    async def test_initial_players_field_is_forwarded_to_use_case(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post(
            "/leagues",
            json=_create_league_body(title="Seeded", initial_players=["Alex", "Daniel"]),
        )
        assert response.status_code == 201
        cmd = mock_create_league_uc.execute.call_args[0][0]
        assert cmd.initial_players == ["Alex", "Daniel"]

    async def test_initial_players_field_is_optional_and_defaults_to_empty(
        self, client: AsyncClient, mock_create_league_uc: AsyncMock
    ) -> None:
        mock_create_league_uc.execute.return_value = CreateLeagueResult(
            league_id="lid", host_token="tok"
        )
        response = await client.post("/leagues", json=_create_league_body(title="No Seed"))
        assert response.status_code == 201
        cmd = mock_create_league_uc.execute.call_args[0][0]
        assert cmd.initial_players == []

    async def test_blank_initial_players_nickname_returns_422(
        self, client: AsyncClient
    ) -> None:
        response = await client.post(
            "/leagues",
            json=_create_league_body(title="Bad Seed", initial_players=["Alex", "   "]),
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /leagues (title prefix search)
# ---------------------------------------------------------------------------


class TestSearchLeaguesByTitlePrefix:
    async def test_returns_200_with_leagues(
        self, client: AsyncClient, mock_search_leagues_uc: AsyncMock
    ) -> None:
        mock_search_leagues_uc.execute.return_value = [
            LeagueListItem(league_id="lid-1", title="Summer League"),
            LeagueListItem(league_id="lid-2", title="Summer Cup"),
        ]
        response = await client.get("/leagues", params={"title_prefix": "sum"})
        assert response.status_code == 200
        data = response.json()
        assert data["leagues"] == [
            {"league_id": "lid-1", "title": "Summer League"},
            {"league_id": "lid-2", "title": "Summer Cup"},
        ]

    async def test_returns_empty_list(self, client: AsyncClient, mock_search_leagues_uc: AsyncMock) -> None:
        mock_search_leagues_uc.execute.return_value = []
        response = await client.get("/leagues", params={"title_prefix": "zzz"})
        assert response.status_code == 200
        assert response.json()["leagues"] == []

    async def test_blank_prefix_after_trim_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/leagues", params={"title_prefix": "   "})
        assert response.status_code == 422

    async def test_missing_title_prefix_returns_422(self, client: AsyncClient) -> None:
        response = await client.get("/leagues")
        assert response.status_code == 422

    async def test_passes_normalized_prefix_and_limit_to_use_case(
        self, client: AsyncClient, mock_search_leagues_uc: AsyncMock
    ) -> None:
        from app.application.use_cases.search_leagues_by_title_prefix_use_case import (
            SearchLeaguesByTitlePrefixQuery,
        )

        mock_search_leagues_uc.execute.return_value = []
        await client.get("/leagues", params={"title_prefix": "  Foo ", "limit": 200})
        mock_search_leagues_uc.execute.assert_awaited_once()
        call = mock_search_leagues_uc.execute.await_args
        q = call.args[0]
        assert isinstance(q, SearchLeaguesByTitlePrefixQuery)
        assert q.title_prefix_normalized == "foo"
        assert q.limit == 200


# ---------------------------------------------------------------------------
# POST /leagues/{league_id}/matches
# ---------------------------------------------------------------------------


class TestSubmitMatchResult:
    _VALID_PAYLOAD = {
        "pair1_nicknames": ["alice", "bob"],
        "pair2_nicknames": ["charlie", "diana"],
        "pair1_score": "6",
        "pair2_score": "3",
    }

    _FAKE_CREATED_AT = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)

    async def test_returns_201_on_success(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.return_value = SubmitMatchResultResult(
            match_id="match-uuid", created_at=self._FAKE_CREATED_AT
        )
        response = await client.post("/leagues/league-id/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 201

    async def test_response_contains_match_id(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.return_value = SubmitMatchResultResult(
            match_id="m-123", created_at=self._FAKE_CREATED_AT
        )
        response = await client.post("/leagues/league-id/matches", json=self._VALID_PAYLOAD)
        body = response.json()
        assert body["match_id"] == "m-123"
        assert body["created_at"].startswith("2026-05-24T12:00:00")

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.post("/leagues/bad-id/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 404

    async def test_same_player_both_pairs_returns_422(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = SamePlayerOnBothPairsError("overlap")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 422

    async def test_same_player_within_pair_returns_422(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = SamePlayerWithinSinglePairError("dup")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 422

    async def test_pair_conflict_returns_409(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = PairConflictError("conflict")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 409

    async def test_duplicate_pair_matchup_returns_409(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        mock_submit_match_uc.execute.side_effect = DuplicatePairMatchupMatchError("dup")
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 409
        assert response.json()["error"] == "DuplicatePairMatchupMatchError"

    async def test_roster_membership_required_returns_422_with_missing_nicknames_payload(
        self, client: AsyncClient, mock_submit_match_uc: AsyncMock
    ) -> None:
        """v6: when `auto_register_players_on_match=false`, the use case
        raises RosterMembershipRequiredError. The HTTP layer must return 422
        and include the structured `missing_nicknames` array verbatim — the
        chat agent and frontend depend on this contract."""
        mock_submit_match_uc.execute.side_effect = RosterMembershipRequiredError(
            "Match submission contains nicknames not on the roster: michael, ryan",
            missing_nicknames=["michael", "ryan"],
        )
        response = await client.post("/leagues/lid/matches", json=self._VALID_PAYLOAD)
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "RosterMembershipRequiredError"
        assert body["missing_nicknames"] == ["michael", "ryan"]
        assert "michael" in body["detail"]

    async def test_pair1_with_one_nickname_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {**self._VALID_PAYLOAD, "pair1_nicknames": ["alice"]}
        response = await client.post("/leagues/lid/matches", json=payload)
        assert response.status_code == 422

    async def test_pair2_with_three_nicknames_returns_422(
        self, client: AsyncClient
    ) -> None:
        payload = {**self._VALID_PAYLOAD, "pair2_nicknames": ["a", "b", "c"]}
        response = await client.post("/leagues/lid/matches", json=payload)
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST/PATCH/DELETE /leagues/{league_id}/singles-matches
# ---------------------------------------------------------------------------


class TestSinglesMatchRoutes:
    _VALID_PAYLOAD = {
        "player1_nickname": "alice",
        "player2_nickname": "bob",
        "player1_score": "6",
        "player2_score": "3",
    }

    _FAKE_CREATED_AT = datetime(2026, 5, 24, 12, 0, 0, tzinfo=timezone.utc)

    async def test_submit_singles_returns_201(
        self, client: AsyncClient, mock_submit_singles_match_uc: AsyncMock
    ) -> None:
        mock_submit_singles_match_uc.execute.return_value = (
            SubmitSinglesMatchResultResult(
                match_id="singles-match-id",
                created_at=self._FAKE_CREATED_AT,
            )
        )

        response = await client.post(
            "/leagues/league-id/singles-matches",
            json=self._VALID_PAYLOAD,
        )

        assert response.status_code == 201
        assert response.json()["match_id"] == "singles-match-id"

    async def test_submit_singles_same_player_returns_422(
        self, client: AsyncClient, mock_submit_singles_match_uc: AsyncMock
    ) -> None:
        mock_submit_singles_match_uc.execute.side_effect = SamePlayerOnBothSidesError(
            "same player"
        )

        response = await client.post(
            "/leagues/league-id/singles-matches",
            json=self._VALID_PAYLOAD,
        )

        assert response.status_code == 422
        assert response.json()["error"] == "SamePlayerOnBothSidesError"

    async def test_edit_singles_player_route_returns_updated_scores(
        self, client: AsyncClient, mock_edit_singles_match_score_uc: AsyncMock
    ) -> None:
        mock_edit_singles_match_score_uc.execute.return_value = (
            UpdatedSinglesMatchResult(
                match_id="match-id",
                player1_score="4",
                player2_score="6",
            )
        )

        response = await client.patch(
            "/leagues/league-id/singles-matches/match-id",
            json={"player1_score": "4", "player2_score": "6"},
        )

        assert response.status_code == 200
        assert response.json()["player1_score"] == "4"

    async def test_delete_singles_player_route_returns_204(
        self, client: AsyncClient, mock_delete_singles_match_uc: AsyncMock
    ) -> None:
        response = await client.delete("/leagues/league-id/singles-matches/match-id")

        assert response.status_code == 204
        mock_delete_singles_match_uc.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/standings
# ---------------------------------------------------------------------------


class TestGetStandings:
    async def test_returns_200_with_standings_list(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[
                StandingsEntry(
                    subject_kind="pair",
                    rank=1,
                    matches_played=3,
                    wins=2,
                    losses=1,
                    games_won=12,
                    games_lost=8,
                    games_diff=4,
                    win_pct=2 / 3,
                    draws=1,
                    pair_id="t1",
                    player1_nickname="alice",
                    player2_nickname="bob",
                )
            ],
            tie_breakers=("matches_won",),
        )
        response = await client.get("/leagues/lid/standings")
        assert response.status_code == 200
        data = response.json()
        assert len(data["standings"]) == 1
        assert data["standings"][0]["subject_kind"] == "pair"
        assert data["standings"][0]["rank"] == 1
        assert data["standings"][0]["wins"] == 2
        assert data["standings"][0]["games_diff"] == 4
        assert data["standings"][0]["draws"] == 1
        assert data["tie_breakers"] == ["matches_won"]

    async def test_response_echoes_league_tie_breakers(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("games_won", "games_diff"),
        )
        response = await client.get("/leagues/lid/standings")
        assert response.status_code == 200
        assert response.json()["tie_breakers"] == ["games_won", "games_diff"]

    async def test_passes_optional_date_filters_to_use_case(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )
        response = await client.get(
            "/leagues/lid/standings?start_date=2026-05-24&end_date=2026-05-25"
        )
        assert response.status_code == 200
        call_args = mock_get_standings_uc.execute.call_args[0][0]
        assert call_args.league_id == "lid"
        assert call_args.start_date == date(2026, 5, 24)
        assert call_args.end_date == date(2026, 5, 25)
        assert call_args.subject is None

    async def test_passes_optional_subject_to_use_case(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )

        response = await client.get("/leagues/lid/standings?subject=player")

        assert response.status_code == 200
        call_args = mock_get_standings_uc.execute.call_args[0][0]
        assert call_args.league_id == "lid"
        assert call_args.subject == "player"

    async def test_passes_optional_scope_to_use_case(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )

        response = await client.get("/leagues/lid/standings?subject=player&scope=both")

        assert response.status_code == 200
        call_args = mock_get_standings_uc.execute.call_args[0][0]
        assert call_args.subject == "player"
        assert call_args.scope == "both"

    async def test_pair_subject_with_non_doubles_scope_returns_422(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        response = await client.get("/leagues/lid/standings?subject=pair&scope=singles")

        assert response.status_code == 422
        mock_get_standings_uc.execute.assert_not_awaited()

    async def test_passes_subject_with_date_filters_to_use_case(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )

        response = await client.get(
            "/leagues/lid/standings?subject=pair"
            "&start_date=2026-05-24&end_date=2026-05-25"
        )

        assert response.status_code == 200
        call_args = mock_get_standings_uc.execute.call_args[0][0]
        assert call_args.subject == "pair"
        assert call_args.start_date == date(2026, 5, 24)
        assert call_args.end_date == date(2026, 5, 25)

    async def test_invalid_subject_returns_422(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        response = await client.get("/leagues/lid/standings?subject=team")

        assert response.status_code == 422
        mock_get_standings_uc.execute.assert_not_awaited()

    async def test_passes_one_sided_date_filters_to_use_case(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )

        start_response = await client.get("/leagues/lid/standings?start_date=2026-05-24")
        assert start_response.status_code == 200
        start_args = mock_get_standings_uc.execute.call_args[0][0]
        assert start_args.start_date == date(2026, 5, 24)
        assert start_args.end_date is None

        end_response = await client.get("/leagues/lid/standings?end_date=2026-05-25")
        assert end_response.status_code == 200
        end_args = mock_get_standings_uc.execute.call_args[0][0]
        assert end_args.start_date is None
        assert end_args.end_date == date(2026, 5, 25)

    async def test_invalid_date_filter_range_returns_422(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        response = await client.get(
            "/leagues/lid/standings?start_date=2026-05-25&end_date=2026-05-24"
        )
        assert response.status_code == 422
        mock_get_standings_uc.execute.assert_not_awaited()

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/standings")
        assert response.status_code == 404

    async def test_empty_standings_returned_as_empty_list(
        self, client: AsyncClient, mock_get_standings_uc: AsyncMock
    ) -> None:
        mock_get_standings_uc.execute.return_value = StandingsView(
            entries=[],
            tie_breakers=("matches_won",),
        )
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
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[
                StandingsEntry(
                    subject_kind="pair",
                    rank=1,
                    matches_played=3,
                    wins=2,
                    losses=1,
                    games_won=12,
                    games_lost=8,
                    games_diff=4,
                    win_pct=2 / 3,
                    pair_id="t1",
                    player1_nickname="alice",
                    player2_nickname="bob",
                )
            ],
            tie_breakers=("matches_won",),
        )
        response = await client.get("/leagues/lid/standings/by-player?player_name=alice")
        assert response.status_code == 200
        data = response.json()
        assert len(data["standings"]) == 1
        assert data["standings"][0]["rank"] == 1
        assert data["standings"][0]["wins"] == 2
        assert data["tie_breakers"] == ["matches_won"]

    async def test_returns_200_with_player_subject_row(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[
                StandingsEntry(
                    subject_kind="player",
                    rank=1,
                    matches_played=3,
                    wins=2,
                    losses=1,
                    games_won=12,
                    games_lost=8,
                    games_diff=4,
                    win_pct=2 / 3,
                    player_id="p1",
                    nickname="alice",
                )
            ],
            tie_breakers=("games_won",),
        )
        response = await client.get("/leagues/lid/standings/by-player?player_name=alice")
        assert response.status_code == 200
        data = response.json()
        assert data["standings"][0]["subject_kind"] == "player"
        assert data["standings"][0]["nickname"] == "alice"
        assert data["standings"][0]["player_id"] == "p1"
        assert data["standings"][0]["pair_id"] is None
        assert data["standings"][0]["draws"] == 0
        assert data["tie_breakers"] == ["games_won"]

    async def test_passes_params_to_use_case(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[], tie_breakers=("matches_won",)
        )
        await client.get(
            "/leagues/lid/standings/by-player?player_name=alice"
            "&start_date=2026-05-24&end_date=2026-05-25"
        )
        call_args = mock_get_standings_by_player_uc.execute.call_args[0][0]
        assert call_args.player_name == "alice"
        assert call_args.league_id == "lid"
        assert call_args.start_date == date(2026, 5, 24)
        assert call_args.end_date == date(2026, 5, 25)

    async def test_passes_scope_to_use_case(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[], tie_breakers=("matches_won",)
        )
        await client.get("/leagues/lid/standings/by-player?player_name=alice&scope=singles")
        call_args = mock_get_standings_by_player_uc.execute.call_args[0][0]
        assert call_args.scope == "singles"

    async def test_passes_one_sided_date_filter_to_use_case(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[], tie_breakers=("matches_won",)
        )

        response = await client.get(
            "/leagues/lid/standings/by-player?player_name=alice&start_date=2026-05-24"
        )

        assert response.status_code == 200
        call_args = mock_get_standings_by_player_uc.execute.call_args[0][0]
        assert call_args.player_name == "alice"
        assert call_args.start_date == date(2026, 5, 24)
        assert call_args.end_date is None

    async def test_invalid_by_player_date_filter_range_returns_422(
        self, client: AsyncClient, mock_get_standings_by_player_uc: AsyncMock
    ) -> None:
        response = await client.get(
            "/leagues/lid/standings/by-player?player_name=alice"
            "&start_date=2026-05-25&end_date=2026-05-24"
        )
        assert response.status_code == 422
        mock_get_standings_by_player_uc.execute.assert_not_awaited()

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
        mock_get_standings_by_player_uc.execute.return_value = StandingsView(
            entries=[], tie_breakers=("matches_won",)
        )
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
                pair1_player1_nickname="alice",
                pair1_player2_nickname="bob",
                pair2_player1_nickname="charlie",
                pair2_player2_nickname="diana",
                pair1_score="6",
                pair2_score="3",
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

    async def test_passes_scope_to_use_case(
        self, client: AsyncClient, mock_get_match_history_uc: AsyncMock
    ) -> None:
        mock_get_match_history_uc.execute.return_value = []
        response = await client.get("/leagues/lid/matches?scope=both")
        assert response.status_code == 200
        call_args = mock_get_match_history_uc.execute.call_args[0][0]
        assert call_args.scope == "both"


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/roster
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# GET /leagues/{league_id}/matches/by-player
# ---------------------------------------------------------------------------


class TestGetMatchHistoryByPlayer:
    _MATCH_RECORD = MatchHistoryRecord(
        match_id="m1",
        pair1_player1_nickname="alice",
        pair1_player2_nickname="bob",
        pair2_player1_nickname="charlie",
        pair2_player2_nickname="diana",
        pair1_score="6",
        pair2_score="3",
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

    async def test_passes_scope_to_use_case(
        self, client: AsyncClient, mock_get_match_history_by_player_uc: AsyncMock
    ) -> None:
        mock_get_match_history_by_player_uc.execute.return_value = []
        await client.get("/leagues/lid/matches/by-player?player_name=alice&scope=singles")
        call_args = mock_get_match_history_by_player_uc.execute.call_args[0][0]
        assert call_args.scope == "singles"

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


_DEFAULT_ROSTER_RULES: dict = {
    "version": 8,
    "pair_matchup_idempotency": "once_per_day",
    "one_pair_per_player": True,
    "ranking_subject": "pair",
    "tie_breakers": ["matches_won"],
    "auto_register_players_on_match": True,
}


class TestGetLeagueRoster:
    async def test_returns_200_with_players_and_pairs(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.return_value = RosterView(
            title="Summer Cup",
            league_timezone="America/Los_Angeles",
            latest_match_date=date(2026, 5, 24),
            latest_match_date_single=date(2026, 5, 25),
            latest_activity_date=date(2026, 5, 25),
            rules=dict(_DEFAULT_ROSTER_RULES),
            players=[
                PlayerEntry(
                    player_id="p1",
                    nickname="alice",
                    aliases=["ali"],
                    rating=3.5,
                )
            ],
            pairs=[PairEntry(pair_id="t1", player1_nickname="alice", player2_nickname="bob")],
        )
        response = await client.get("/leagues/lid/roster")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Summer Cup"
        assert data["league_timezone"] == "America/Los_Angeles"
        assert data["latest_match_date"] == "2026-05-24"
        assert data["latest_match_date_single"] == "2026-05-25"
        assert data["latest_activity_date"] == "2026-05-25"
        assert len(data["players"]) == 1
        assert data["players"][0]["nickname"] == "alice"
        assert data["players"][0]["aliases"] == ["ali"]
        assert data["players"][0]["rating"] == 3.5
        assert len(data["pairs"]) == 1
        assert data["rules"] == _DEFAULT_ROSTER_RULES

    async def test_league_not_found_returns_404(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.side_effect = LeagueNotFoundError("not found")
        response = await client.get("/leagues/bad-id/roster")
        assert response.status_code == 404

    async def test_empty_roster_returns_empty_lists(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        mock_get_roster_uc.execute.return_value = RosterView(
            title="Empty League",
            league_timezone="America/Los_Angeles",
            rules=dict(_DEFAULT_ROSTER_RULES),
            players=[],
            pairs=[],
        )
        response = await client.get("/leagues/lid/roster")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Empty League"
        assert data["players"] == []
        assert data["pairs"] == []
        assert data["rules"] == _DEFAULT_ROSTER_RULES

    async def test_response_echoes_one_pair_per_player_false(
        self, client: AsyncClient, mock_get_roster_uc: AsyncMock
    ) -> None:
        """v3+: leagues created with `one_pair_per_player=false` must surface
        that flag verbatim so the chat UI can suppress the partner-conflict
        warning emitted by `renderMatchSubmitRosterNotes`."""
        rules = dict(_DEFAULT_ROSTER_RULES)
        rules["one_pair_per_player"] = False
        rules["ranking_subject"] = "player"
        mock_get_roster_uc.execute.return_value = RosterView(
            title="Open Roster",
            league_timezone="America/Los_Angeles",
            rules=rules,
            players=[],
            pairs=[],
        )
        response = await client.get("/leagues/lid/roster")
        assert response.status_code == 200
        data = response.json()
        assert data["rules"]["one_pair_per_player"] is False
        assert data["rules"]["ranking_subject"] == "player"
