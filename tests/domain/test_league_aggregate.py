"""Unit tests for the League aggregate root.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import uuid

import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import (
    AllowlistEntryNotFoundError,
    AllowlistNicknameAlreadyExistsError,
    NicknameAlreadyInUseError,
    NotInAllowlistError,
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

    def test_default_rules_use_once_per_league_for_new_product_leagues(self) -> None:
        league = _league()
        assert league.rules == LeagueRules.default_for_new_league()


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
        # Only charlie is a new player; alice already existed.
        assert len(new_players) == 1
        assert new_players[0].nickname.value == "charlie"

    def test_player_on_three_teams_when_otpp_false(self) -> None:
        league = _league_otpp_false()
        league.register_players_and_team("alice", "bob")
        league.register_players_and_team("alice", "charlie")
        league.register_players_and_team("alice", "diana")

        assert len(league.teams) == 3
        # Alice is exactly one Player record (registered once, partnered three times).
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
# Helpers for the allowlist test classes
# ---------------------------------------------------------------------------


def _league_require_allowlist(title: str = "Allowlist League") -> League:
    """League configured with v5 `require_allowlist=true`."""
    rules = LeagueRules.from_dict(
        {
            "version": 5,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_allowlist": True,
        }
    )
    return League.create(title=title, description=None, host_token="test-token", rules=rules)


# ---------------------------------------------------------------------------
# League.add_allowlist_entries
# ---------------------------------------------------------------------------


class TestAddAllowlistEntries:
    def test_adds_single_nickname(self) -> None:
        league = _league()
        added = league.add_allowlist_entries(["alex"])
        assert len(added) == 1
        assert added[0].nickname.value == "alex"
        assert league.allowlist == added

    def test_adds_multiple_nicknames_atomically(self) -> None:
        league = _league()
        added = league.add_allowlist_entries(["alex", "daniel", "jason"])
        assert [e.nickname.value for e in added] == ["alex", "daniel", "jason"]
        assert {e.nickname.value for e in league.allowlist} == {
            "alex",
            "daniel",
            "jason",
        }

    def test_normalizes_to_lowercase(self) -> None:
        league = _league()
        league.add_allowlist_entries(["Alex Kim", "DANIEL"])
        nicks = {e.nickname.value for e in league.allowlist}
        assert nicks == {"alex kim", "daniel"}

    def test_each_entry_gets_unique_id(self) -> None:
        league = _league()
        added = league.add_allowlist_entries(["alex", "daniel"])
        assert added[0].allowlist_entry_id != added[1].allowlist_entry_id

    def test_duplicate_against_existing_raises(self) -> None:
        league = _league()
        league.add_allowlist_entries(["alex"])
        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            league.add_allowlist_entries(["alex"])

    def test_duplicate_against_existing_case_insensitive(self) -> None:
        league = _league()
        league.add_allowlist_entries(["Alex"])
        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            league.add_allowlist_entries(["ALEX"])

    def test_duplicate_within_same_batch_raises(self) -> None:
        league = _league()
        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            league.add_allowlist_entries(["alex", "Alex"])

    def test_failed_batch_makes_no_partial_inserts(self) -> None:
        league = _league()
        league.add_allowlist_entries(["alex"])
        with pytest.raises(AllowlistNicknameAlreadyExistsError):
            league.add_allowlist_entries(["daniel", "alex"])
        # daniel should NOT have been added.
        nicks = {e.nickname.value for e in league.allowlist}
        assert nicks == {"alex"}

    def test_empty_list_raises_value_error(self) -> None:
        league = _league()
        with pytest.raises(ValueError):
            league.add_allowlist_entries([])

    def test_allowlist_independent_of_roster(self) -> None:
        """A nickname can be in the allowlist without being on the roster."""
        league = _league()
        league.add_allowlist_entries(["alex", "daniel"])
        assert league.players == []
        assert league.teams == []


# ---------------------------------------------------------------------------
# League.remove_allowlist_entry
# ---------------------------------------------------------------------------


class TestRemoveAllowlistEntry:
    def test_removes_entry(self) -> None:
        league = _league()
        added = league.add_allowlist_entries(["alex", "daniel"])
        league.remove_allowlist_entry(str(added[0].allowlist_entry_id.value))
        nicks = {e.nickname.value for e in league.allowlist}
        assert nicks == {"daniel"}

    def test_removed_id_appended_to_pending_list(self) -> None:
        league = _league()
        added = league.add_allowlist_entries(["alex"])
        league.remove_allowlist_entry(str(added[0].allowlist_entry_id.value))
        assert added[0].allowlist_entry_id in league.pending_deleted_allowlist_entry_ids

    def test_unknown_id_raises(self) -> None:
        league = _league()
        with pytest.raises(AllowlistEntryNotFoundError):
            league.remove_allowlist_entry(str(uuid.uuid4()))

    def test_remove_does_not_touch_roster(self) -> None:
        """Removing an allowlist nickname must NOT delete a roster Player
        record with the same nickname (the two are decoupled by design)."""
        league = _league()
        league.register_players_and_team("alex", "daniel")  # creates Player rows
        added = league.add_allowlist_entries(["alex", "daniel"])
        league.remove_allowlist_entry(str(added[0].allowlist_entry_id.value))
        roster = {p.nickname.value for p in league.players}
        assert roster == {"alex", "daniel"}


# ---------------------------------------------------------------------------
# League.validate_match_participants_allowed
# ---------------------------------------------------------------------------


class TestValidateMatchParticipantsAllowed:
    def test_noop_when_flag_off(self) -> None:
        """Default leagues have require_allowlist=False; validation is a
        no-op even when the allowlist is empty."""
        league = _league()
        # Should not raise even though allowlist is empty.
        league.validate_match_participants_allowed(["alice", "bob", "charlie", "diana"])

    def test_passes_when_all_nicknames_allowed(self) -> None:
        league = _league_require_allowlist()
        league.add_allowlist_entries(["alice", "bob", "charlie", "diana"])
        league.validate_match_participants_allowed(
            ["alice", "bob", "charlie", "diana"]
        )

    def test_normalizes_input_before_checking(self) -> None:
        league = _league_require_allowlist()
        league.add_allowlist_entries(["alice", "bob", "charlie", "diana"])
        league.validate_match_participants_allowed(
            ["ALICE", "Bob ", " charlie", "DIANA"]
        )

    def test_raises_with_missing_nicknames_when_flag_on(self) -> None:
        league = _league_require_allowlist()
        league.add_allowlist_entries(["alice", "bob"])
        with pytest.raises(NotInAllowlistError) as exc:
            league.validate_match_participants_allowed(
                ["alice", "bob", "michael", "ryan"]
            )
        assert exc.value.missing_nicknames == ["michael", "ryan"]

    def test_missing_list_is_normalized_lowercase(self) -> None:
        league = _league_require_allowlist()
        league.add_allowlist_entries(["alice"])
        with pytest.raises(NotInAllowlistError) as exc:
            league.validate_match_participants_allowed(
                ["alice", "MICHAEL", "michael", "RYAN"]
            )
        # Deduped, lowercased, in input order of first appearance.
        assert exc.value.missing_nicknames == ["michael", "ryan"]

    def test_message_mentions_missing_nicknames(self) -> None:
        league = _league_require_allowlist()
        league.add_allowlist_entries(["alice", "bob"])
        with pytest.raises(NotInAllowlistError) as exc:
            league.validate_match_participants_allowed(
                ["alice", "bob", "michael", "ryan"]
            )
        msg = str(exc.value)
        assert "michael" in msg
        assert "ryan" in msg

    def test_empty_allowlist_with_flag_on_rejects_all(self) -> None:
        league = _league_require_allowlist()
        with pytest.raises(NotInAllowlistError) as exc:
            league.validate_match_participants_allowed(
                ["alice", "bob", "charlie", "diana"]
            )
        assert exc.value.missing_nicknames == ["alice", "bob", "charlie", "diana"]

    def test_dedupes_in_batch_when_same_missing_nickname_appears_twice(self) -> None:
        league = _league_require_allowlist()
        with pytest.raises(NotInAllowlistError) as exc:
            league.validate_match_participants_allowed(["alice", "alice", "bob"])
        assert exc.value.missing_nicknames == ["alice", "bob"]
