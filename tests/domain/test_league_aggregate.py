"""Unit tests for the League aggregate root.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import uuid

import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.exceptions import (
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
    TeamNotFoundError,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _league(title: str = "Test League") -> League:
    return League.create(title=title, description=None, host_token="test-token")


# ---------------------------------------------------------------------------
# League.create
# ---------------------------------------------------------------------------


class TestLeagueCreate:
    def test_creates_league_with_empty_roster(self) -> None:
        league = _league()
        assert league.players == []
        assert league.teams == []

    def test_stores_title_as_provided(self) -> None:
        league = _league("My League")
        assert league.title == "My League"

    def test_stores_description(self) -> None:
        league = League.create("Title", "A description", "token")
        assert league.description == "A description"

    def test_description_can_be_none(self) -> None:
        league = League.create("Title", None, "token")
        assert league.description is None

    def test_stores_host_token(self) -> None:
        league = League.create("L", None, "my-host-token")
        assert league.host_token.value == "my-host-token"

    def test_generates_unique_league_id(self) -> None:
        l1 = _league("L1")
        l2 = _league("L2")
        assert l1.league_id != l2.league_id

    def test_blank_title_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("", None, "token")

    def test_whitespace_only_title_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("   ", None, "token")

    def test_pending_deleted_team_ids_initialised_empty(self) -> None:
        league = _league()
        assert league.pending_deleted_team_ids == []


# ---------------------------------------------------------------------------
# League.register_players_and_team
# ---------------------------------------------------------------------------


class TestRegisterPlayersAndTeam:
    def test_two_new_players_create_two_players_and_one_team(self) -> None:
        league = _league()
        new_players, team = league.register_players_and_team("Alice", "Bob")
        assert len(new_players) == 2
        assert len(league.players) == 2
        assert len(league.teams) == 1
        assert team in league.teams

    def test_nicknames_are_normalised_to_lowercase(self) -> None:
        league = _league()
        league.register_players_and_team("ALICE", "BOB")
        nicknames = {p.nickname.value for p in league.players}
        assert nicknames == {"alice", "bob"}

    def test_same_player_listed_twice_raises_same_player_error(self) -> None:
        league = _league()
        with pytest.raises(SamePlayerWithinSingleTeamError):
            league.register_players_and_team("alice", "alice")

    def test_same_player_case_insensitive_raises(self) -> None:
        league = _league()
        with pytest.raises(SamePlayerWithinSingleTeamError):
            league.register_players_and_team("Alice", "ALICE")

    def test_repeat_call_with_same_pair_returns_existing_team(self) -> None:
        league = _league()
        _, team1 = league.register_players_and_team("alice", "bob")
        new_players, team2 = league.register_players_and_team("alice", "bob")
        assert team1.team_id == team2.team_id
        assert new_players == []
        assert len(league.teams) == 1

    def test_existing_player_paired_with_existing_partner_no_new_players(self) -> None:
        league = _league()
        league.register_players_and_team("alice", "bob")
        new_players, _ = league.register_players_and_team("alice", "bob")
        assert new_players == []

    def test_player_on_existing_team_cannot_join_new_team(self) -> None:
        league = _league()
        league.register_players_and_team("alice", "bob")
        with pytest.raises(TeamConflictError):
            league.register_players_and_team("alice", "charlie")

    def test_both_players_on_different_teams_raises_conflict(self) -> None:
        league = _league()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("charlie", "diana")
        with pytest.raises(TeamConflictError):
            league.register_players_and_team("alice", "charlie")

    def test_new_player_paired_with_existing_free_player_succeeds(self) -> None:
        league = _league()
        _, team1 = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team1.team_id.value))
        new_players, team2 = league.register_players_and_team("alice", "charlie")
        assert len(league.teams) == 1
        assert len(new_players) == 1  # only charlie is new

    def test_team_id_is_unique_per_new_team(self) -> None:
        league = _league()
        _, team1 = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team1.team_id.value))
        _, team2 = league.register_players_and_team("charlie", "diana")
        assert team1.team_id != team2.team_id

    def test_player_ids_within_team_are_sorted_consistently(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        pid1_str = str(team.player_id_1.value)
        pid2_str = str(team.player_id_2.value)
        assert pid1_str <= pid2_str


# ---------------------------------------------------------------------------
# League.edit_player_nickname
# ---------------------------------------------------------------------------


class TestEditPlayerNickname:
    def _league_with_players(self) -> League:
        league = _league()
        league.register_players_and_team("alice", "bob")
        return league

    def _get_player(self, league: League, nickname: str):  # type: ignore[return]
        return next(p for p in league.players if p.nickname.value == nickname)

    def test_edits_nickname_successfully(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        updated = league.edit_player_nickname(str(alice.player_id.value), "alicia")
        assert updated.nickname.value == "alicia"

    def test_edits_nickname_is_lowercased(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        updated = league.edit_player_nickname(str(alice.player_id.value), "ALICIA")
        assert updated.nickname.value == "alicia"

    def test_player_not_found_raises(self) -> None:
        league = self._league_with_players()
        with pytest.raises(PlayerNotFoundError):
            league.edit_player_nickname(str(uuid.uuid4()), "newname")

    def test_duplicate_nickname_raises(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        with pytest.raises(NicknameAlreadyInUseError):
            league.edit_player_nickname(str(alice.player_id.value), "bob")

    def test_same_nickname_on_same_player_does_not_raise(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        updated = league.edit_player_nickname(str(alice.player_id.value), "alice")
        assert updated.nickname.value == "alice"

    def test_case_insensitive_duplicate_detection(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        with pytest.raises(NicknameAlreadyInUseError):
            league.edit_player_nickname(str(alice.player_id.value), "BOB")

    def test_nickname_updated_in_league_player_list(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.edit_player_nickname(str(alice.player_id.value), "alicia")
        nicknames = {p.nickname.value for p in league.players}
        assert "alicia" in nicknames
        assert "alice" not in nicknames


# ---------------------------------------------------------------------------
# League.delete_team
# ---------------------------------------------------------------------------


class TestDeleteTeam:
    def test_deletes_team_successfully(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))
        assert len(league.teams) == 0

    def test_players_remain_after_team_deletion(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))
        assert len(league.players) == 2

    def test_deleted_team_id_added_to_pending_list(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))
        assert team.team_id in league.pending_deleted_team_ids

    def test_team_not_found_raises(self) -> None:
        league = _league()
        with pytest.raises(TeamNotFoundError):
            league.delete_team(str(uuid.uuid4()))

    def test_deletes_only_specified_team(self) -> None:
        league = _league()
        _, team1 = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team1.team_id.value))
        _, team2 = league.register_players_and_team("charlie", "diana")
        assert len(league.teams) == 1
        assert league.teams[0].team_id == team2.team_id

    def test_delete_already_deleted_team_raises(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team.team_id.value))
        with pytest.raises(TeamNotFoundError):
            league.delete_team(str(team.team_id.value))
