"""Unit tests for the League aggregate root.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import uuid

import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.entities import Player
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname
from app.domain.exceptions import (
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
    TeamNotFoundError,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _league(title: str = "Test League") -> League:
    return League.create(title=title, description=None, host_token="test-token")


def _league_otpp_false(title: str = "OTPP-False League") -> League:
    """League configured with v3 `(team, OTPP=false)` rules."""
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    return League.create(title=title, description=None, host_token="test-token", rules=rules)


def _league_require_roster() -> League:
    """League configured with v6 `auto_register_players_on_match=False`.

    Pre-registered players are the only ones allowed to submit matches.
    """
    rules = LeagueRules.from_dict(
        {
            "version": 6,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": False,
        }
    )
    return League.create(
        title="Roster-Only League",
        description=None,
        host_token="test-token",
        rules=rules,
    )


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

    def test_pending_deleted_player_ids_initialised_empty(self) -> None:
        league = _league()
        assert league.pending_deleted_player_ids == []

    def test_default_rules_use_auto_register_true_for_new_product_leagues(self) -> None:
        league = _league()
        assert league.rules == LeagueRules.default_for_new_league()
        assert league.rules.auto_register_players_on_match is True


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
        assert len(new_players) == 1

    def test_team_id_is_unique_per_new_team(self) -> None:
        league = _league()
        _, team1 = league.register_players_and_team("alice", "bob")
        league.delete_team(str(team1.team_id.value))
        _, team2 = league.register_players_and_team("charlie", "diana")
        assert team1.team_id != team2.team_id

    def test_player1_in_team_is_alphabetically_first_by_nickname(self) -> None:
        league = _league()
        _, team = league.register_players_and_team("alice", "bob")
        p1 = next(p for p in league.players if p.player_id == team.player_id_1)
        p2 = next(p for p in league.players if p.player_id == team.player_id_2)
        assert p1.nickname.value <= p2.nickname.value

    def test_player_order_is_alphabetical_regardless_of_input_order(self) -> None:
        league1 = _league("L1")
        _, team1 = league1.register_players_and_team("zed", "aime")

        league2 = League.create("L2", None, "token")
        _, team2 = league2.register_players_and_team("aime", "zed")

        p1_league1 = next(p for p in league1.players if p.player_id == team1.player_id_1)
        p1_league2 = next(p for p in league2.players if p.player_id == team2.player_id_1)
        assert p1_league1.nickname.value == "aime"
        assert p1_league2.nickname.value == "aime"


# ---------------------------------------------------------------------------
# v3: register_players_and_team under one_team_per_player=False
# ---------------------------------------------------------------------------


class TestRegisterPlayersAndTeamOTPPFalse:
    def test_player_can_join_second_team_when_otpp_false(self) -> None:
        league = _league_otpp_false()
        _, team_ab = league.register_players_and_team("alice", "bob")
        new_players, team_ac = league.register_players_and_team("alice", "charlie")

        assert team_ab.team_id != team_ac.team_id
        assert len(league.teams) == 2
        assert len(new_players) == 1
        assert new_players[0].nickname.value == "charlie"

    def test_player_on_three_teams_when_otpp_false(self) -> None:
        league = _league_otpp_false()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("alice", "charlie")
        league.register_players_and_team("alice", "diana")

        assert len(league.teams) == 3
        nicknames = [p.nickname.value for p in league.players]
        assert nicknames.count("alice") == 1
        assert {"alice", "bob", "charlie", "diana"} == set(nicknames)

    def test_otpp_true_still_rejects_second_team_for_same_player(self) -> None:
        """Regression: OTPP=true is still the default for new leagues."""
        league = _league()
        league.register_players_and_team("alice", "bob")
        with pytest.raises(TeamConflictError):
            league.register_players_and_team("alice", "charlie")


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


# ---------------------------------------------------------------------------
# League.add_players
# ---------------------------------------------------------------------------


class TestAddPlayers:
    def test_adds_single_nickname(self) -> None:
        league = _league()
        added = league.add_players(["alex"])
        assert len(added) == 1
        assert added[0].nickname.value == "alex"
        assert {p.nickname.value for p in league.players} == {"alex"}

    def test_adds_multiple_nicknames_atomically(self) -> None:
        league = _league()
        added = league.add_players(["alex", "daniel", "jason"])
        assert [p.nickname.value for p in added] == ["alex", "daniel", "jason"]
        assert {p.nickname.value for p in league.players} == {
            "alex",
            "daniel",
            "jason",
        }

    def test_normalizes_to_lowercase(self) -> None:
        league = _league()
        league.add_players(["Alex Kim", "DANIEL"])
        nicks = {p.nickname.value for p in league.players}
        assert nicks == {"alex kim", "daniel"}

    def test_each_player_gets_unique_id(self) -> None:
        league = _league()
        added = league.add_players(["alex", "daniel"])
        assert added[0].player_id != added[1].player_id

    def test_duplicate_against_existing_roster_raises(self) -> None:
        league = _league()
        league.add_players(["alex"])
        with pytest.raises(NicknameAlreadyInUseError):
            league.add_players(["alex"])

    def test_duplicate_against_existing_case_insensitive(self) -> None:
        league = _league()
        league.add_players(["Alex"])
        with pytest.raises(NicknameAlreadyInUseError):
            league.add_players(["ALEX"])

    def test_duplicate_within_same_batch_raises(self) -> None:
        league = _league()
        with pytest.raises(NicknameAlreadyInUseError):
            league.add_players(["alex", "Alex"])

    def test_failed_batch_makes_no_partial_inserts(self) -> None:
        league = _league()
        league.add_players(["alex"])
        with pytest.raises(NicknameAlreadyInUseError):
            league.add_players(["daniel", "alex"])
        nicks = {p.nickname.value for p in league.players}
        assert nicks == {"alex"}

    def test_empty_list_raises_value_error(self) -> None:
        league = _league()
        with pytest.raises(ValueError):
            league.add_players([])

    def test_add_players_does_not_create_teams(self) -> None:
        """Teams are still created only inside register_players_and_team."""
        league = _league()
        league.add_players(["alex", "daniel"])
        assert league.teams == []

    def test_pre_registered_player_is_reused_by_match_submission(self) -> None:
        """When a host pre-registers a player and that player later submits a
        match, register_players_and_team finds the existing Player rather
        than creating a duplicate."""
        league = _league()
        added = league.add_players(["alex", "daniel"])
        before_ids = {p.player_id for p in league.players}

        new_players, _ = league.register_players_and_team("alex", "daniel")

        assert new_players == []
        assert {p.player_id for p in league.players} == before_ids
        assert {p.player_id for p in added} == before_ids


# ---------------------------------------------------------------------------
# League.remove_player
# ---------------------------------------------------------------------------


class TestRemovePlayer:
    def test_removes_player_with_no_participation(self) -> None:
        league = _league()
        added = league.add_players(["alex", "daniel"])
        league.remove_player(str(added[0].player_id.value))
        nicks = {p.nickname.value for p in league.players}
        assert nicks == {"daniel"}

    def test_removed_id_appended_to_pending_list(self) -> None:
        league = _league()
        added = league.add_players(["alex"])
        league.remove_player(str(added[0].player_id.value))
        assert added[0].player_id in league.pending_deleted_player_ids

    def test_unknown_player_id_raises(self) -> None:
        league = _league()
        with pytest.raises(PlayerNotFoundError):
            league.remove_player(str(uuid.uuid4()))

    def test_rejects_player_with_team_membership(self) -> None:
        league = _league()
        league.register_players_and_team("alex", "daniel")
        alex = next(p for p in league.players if p.nickname.value == "alex")

        with pytest.raises(PlayerHasParticipationError) as exc:
            league.remove_player(str(alex.player_id.value))

        assert exc.value.teams_count == 1
        assert exc.value.matches_count == 0
        assert {p.nickname.value for p in league.players} == {"alex", "daniel"}

    def test_rejects_player_with_match_participation(self) -> None:
        """Even when the team is gone but match_count was loaded by the repo
        as > 0 (defensive — in practice the FK keeps the team alive), the
        guard still blocks deletion."""
        league = _league()
        league.add_players(["alex"])
        alex = league.players[0]
        alex.match_count = 3

        with pytest.raises(PlayerHasParticipationError) as exc:
            league.remove_player(str(alex.player_id.value))

        assert exc.value.matches_count == 3

    def test_payload_carries_player_id(self) -> None:
        league = _league()
        league.register_players_and_team("alex", "daniel")
        alex = next(p for p in league.players if p.nickname.value == "alex")

        with pytest.raises(PlayerHasParticipationError) as exc:
            league.remove_player(str(alex.player_id.value))

        assert exc.value.player_id == str(alex.player_id.value)

    def test_does_not_add_to_pending_when_guard_blocks(self) -> None:
        league = _league()
        league.register_players_and_team("alex", "daniel")
        alex = next(p for p in league.players if p.nickname.value == "alex")

        with pytest.raises(PlayerHasParticipationError):
            league.remove_player(str(alex.player_id.value))

        assert alex.player_id not in league.pending_deleted_player_ids


# ---------------------------------------------------------------------------
# League.validate_match_participants_on_roster
# ---------------------------------------------------------------------------


class TestValidateMatchParticipantsOnRoster:
    def test_noop_when_auto_register_true(self) -> None:
        """Default leagues have auto_register_players_on_match=True;
        validation is a no-op even when the roster is empty."""
        league = _league()
        league.validate_match_participants_on_roster(
            ["alice", "bob", "charlie", "diana"]
        )

    def test_passes_when_all_nicknames_on_roster(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob", "charlie", "diana"])
        league.validate_match_participants_on_roster(
            ["alice", "bob", "charlie", "diana"]
        )

    def test_normalizes_input_before_checking(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob", "charlie", "diana"])
        league.validate_match_participants_on_roster(
            ["ALICE", "Bob ", " charlie", "DIANA"]
        )

    def test_raises_with_missing_nicknames_when_flag_off(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob"])
        with pytest.raises(RosterMembershipRequiredError) as exc:
            league.validate_match_participants_on_roster(
                ["alice", "bob", "michael", "ryan"]
            )
        assert exc.value.missing_nicknames == ["michael", "ryan"]

    def test_missing_list_is_normalized_lowercase(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice"])
        with pytest.raises(RosterMembershipRequiredError) as exc:
            league.validate_match_participants_on_roster(
                ["alice", "MICHAEL", "michael", "RYAN"]
            )
        assert exc.value.missing_nicknames == ["michael", "ryan"]

    def test_message_mentions_missing_nicknames(self) -> None:
        league = _league_require_roster()
        league.add_players(["alice", "bob"])
        with pytest.raises(RosterMembershipRequiredError) as exc:
            league.validate_match_participants_on_roster(
                ["alice", "bob", "michael", "ryan"]
            )
        msg = str(exc.value)
        assert "michael" in msg
        assert "ryan" in msg

    def test_empty_roster_with_flag_off_rejects_all(self) -> None:
        league = _league_require_roster()
        with pytest.raises(RosterMembershipRequiredError) as exc:
            league.validate_match_participants_on_roster(
                ["alice", "bob", "charlie", "diana"]
            )
        assert exc.value.missing_nicknames == ["alice", "bob", "charlie", "diana"]

    def test_dedupes_in_batch_when_same_missing_nickname_appears_twice(self) -> None:
        league = _league_require_roster()
        with pytest.raises(RosterMembershipRequiredError) as exc:
            league.validate_match_participants_on_roster(["alice", "alice", "bob"])
        assert exc.value.missing_nicknames == ["alice", "bob"]
