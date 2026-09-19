"""Unit tests for the League aggregate root.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import uuid

import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.entities import Player
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import (
    DEFAULT_LEAGUE_TIMEZONE,
    PlayerId,
    PlayerNickname,
)
from app.domain.exceptions import (
    CannotRemoveCanonicalNicknameError,
    InvalidLeagueRulesError,
    InvalidPlayerRatingError,
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
    PairConflictError,
    PairNotFoundError,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


_TEST_HOST_EMAIL = "host@example.com"


def _league(title: str = "Test League") -> League:
    return League.create(
        title=title,
        description=None,
        host_token="test-token",
        host_email=_TEST_HOST_EMAIL,
    )


def _league_otpp_false(title: str = "OTPP-False League") -> League:
    """League configured with v3 `(pair, OTPP=false)` rules."""
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": False,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
        }
    )
    return League.create(
        title=title,
        description=None,
        host_token="test-token",
        host_email=_TEST_HOST_EMAIL,
        rules=rules,
    )


def _league_require_roster() -> League:
    """League configured with v6 `auto_register_players_on_match=False`.

    Pre-registered players are the only ones allowed to submit matches.
    """
    rules = LeagueRules.from_dict(
        {
            "version": 6,
            "pair_matchup_idempotency": "once_per_league",
            "one_pair_per_player": True,
            "ranking_subject": "pair",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": False,
        }
    )
    return League.create(
        title="Roster-Only League",
        description=None,
        host_token="test-token",
        host_email=_TEST_HOST_EMAIL,
        rules=rules,
    )


# ---------------------------------------------------------------------------
# League.create
# ---------------------------------------------------------------------------


class TestLeagueCreate:
    def test_creates_league_with_empty_roster(self) -> None:
        league = _league()
        assert league.players == []
        assert league.pairs == []

    def test_stores_title_as_provided(self) -> None:
        league = _league("My League")
        assert league.title == "My League"

    def test_stores_description(self) -> None:
        league = League.create("Title", "A description", "token", host_email=_TEST_HOST_EMAIL)
        assert league.description == "A description"

    def test_description_can_be_none(self) -> None:
        league = League.create("Title", None, "token", host_email=_TEST_HOST_EMAIL)
        assert league.description is None

    def test_stores_host_token(self) -> None:
        league = League.create("L", None, "my-host-token", host_email=_TEST_HOST_EMAIL)
        assert league.host_token.value == "my-host-token"

    def test_stores_host_email_normalized(self) -> None:
        league = League.create("L", None, "token", host_email="Host@Example.COM")
        assert league.host_email.value == "host@example.com"

    def test_defaults_league_timezone_to_pacific_time(self) -> None:
        league = _league()
        assert league.league_timezone.value == DEFAULT_LEAGUE_TIMEZONE

    def test_stores_custom_league_timezone(self) -> None:
        league = League.create(
            "L",
            None,
            "token",
            host_email=_TEST_HOST_EMAIL,
            league_timezone="Asia/Seoul",
        )
        assert league.league_timezone.value == "Asia/Seoul"

    def test_invalid_league_timezone_raises_invalid_rules_error(self) -> None:
        with pytest.raises(InvalidLeagueRulesError):
            League.create(
                "L",
                None,
                "token",
                host_email=_TEST_HOST_EMAIL,
                league_timezone="not/a-zone",
            )

    def test_blank_host_email_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("L", None, "token", host_email="")

    def test_whitespace_only_host_email_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("L", None, "token", host_email="   ")

    def test_generates_unique_league_id(self) -> None:
        l1 = _league("L1")
        l2 = _league("L2")
        assert l1.league_id != l2.league_id

    def test_blank_title_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("", None, "token", host_email=_TEST_HOST_EMAIL)

    def test_whitespace_only_title_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            League.create("   ", None, "token", host_email=_TEST_HOST_EMAIL)

    def test_pending_deleted_pair_ids_initialised_empty(self) -> None:
        league = _league()
        assert league.pending_deleted_pair_ids == []

    def test_pending_deleted_player_ids_initialised_empty(self) -> None:
        league = _league()
        assert league.pending_deleted_player_ids == []

    def test_default_rules_use_auto_register_true_for_new_product_leagues(self) -> None:
        league = _league()
        assert league.rules == LeagueRules.default_for_new_league()
        assert league.rules.auto_register_players_on_match is True


# ---------------------------------------------------------------------------
# League.register_players_and_pair
# ---------------------------------------------------------------------------


class TestRegisterSinglePlayer:
    def test_creates_player_without_creating_pair(self) -> None:
        league = _league()

        player = league.register_single_player("Alice")

        assert player.nickname.value == "alice"
        assert len(league.players) == 1
        assert league.pairs == []

    def test_reuses_existing_player_by_alias_or_canonical_nickname(self) -> None:
        league = _league()
        player = league.add_players(["Alice"])[0]
        league.add_alias_to_player(str(player.player_id.value), "Ace")

        found = league.register_single_player("ACE")

        assert found.player_id == player.player_id
        assert len(league.players) == 1
        assert league.pairs == []


class TestRegisterPlayersAndPair:
    def test_two_new_players_create_two_players_and_one_pair(self) -> None:
        league = _league()
        new_players, pair = league.register_players_and_pair("Alice", "Bob")
        assert len(new_players) == 2
        assert len(league.players) == 2
        assert len(league.pairs) == 1
        assert pair in league.pairs

    def test_nicknames_are_normalised_to_lowercase(self) -> None:
        league = _league()
        league.register_players_and_pair("ALICE", "BOB")
        nicknames = {p.nickname.value for p in league.players}
        assert nicknames == {"alice", "bob"}

    def test_same_player_listed_twice_raises_same_player_error(self) -> None:
        league = _league()
        with pytest.raises(SamePlayerWithinSinglePairError):
            league.register_players_and_pair("alice", "alice")

    def test_same_player_case_insensitive_raises(self) -> None:
        league = _league()
        with pytest.raises(SamePlayerWithinSinglePairError):
            league.register_players_and_pair("Alice", "ALICE")

    def test_repeat_call_with_same_pair_returns_existing_pair(self) -> None:
        league = _league()
        _, pair1 = league.register_players_and_pair("alice", "bob")
        new_players, pair2 = league.register_players_and_pair("alice", "bob")
        assert pair1.pair_id == pair2.pair_id
        assert new_players == []
        assert len(league.pairs) == 1

    def test_existing_player_paired_with_existing_partner_no_new_players(self) -> None:
        league = _league()
        league.register_players_and_pair("alice", "bob")
        new_players, _ = league.register_players_and_pair("alice", "bob")
        assert new_players == []

    def test_player_on_existing_pair_cannot_join_new_pair(self) -> None:
        league = _league()
        league.register_players_and_pair("alice", "bob")
        with pytest.raises(PairConflictError):
            league.register_players_and_pair("alice", "charlie")

    def test_both_players_on_different_pairs_raises_conflict(self) -> None:
        league = _league()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("charlie", "diana")
        with pytest.raises(PairConflictError):
            league.register_players_and_pair("alice", "charlie")

    def test_new_player_paired_with_existing_free_player_succeeds(self) -> None:
        league = _league()
        _, pair1 = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair1.pair_id.value))
        new_players, pair2 = league.register_players_and_pair("alice", "charlie")
        assert len(league.pairs) == 1
        assert len(new_players) == 1

    def test_pair_id_is_unique_per_new_pair(self) -> None:
        league = _league()
        _, pair1 = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair1.pair_id.value))
        _, pair2 = league.register_players_and_pair("charlie", "diana")
        assert pair1.pair_id != pair2.pair_id

    def test_player1_in_pair_is_alphabetically_first_by_nickname(self) -> None:
        league = _league()
        _, pair = league.register_players_and_pair("alice", "bob")
        p1 = next(p for p in league.players if p.player_id == pair.player_id_1)
        p2 = next(p for p in league.players if p.player_id == pair.player_id_2)
        assert p1.nickname.value <= p2.nickname.value

    def test_player_order_is_alphabetical_regardless_of_input_order(self) -> None:
        league1 = _league("L1")
        _, pair1 = league1.register_players_and_pair("zed", "aime")

        league2 = League.create("L2", None, "token", host_email=_TEST_HOST_EMAIL)
        _, pair2 = league2.register_players_and_pair("aime", "zed")

        p1_league1 = next(p for p in league1.players if p.player_id == pair1.player_id_1)
        p1_league2 = next(p for p in league2.players if p.player_id == pair2.player_id_1)
        assert p1_league1.nickname.value == "aime"
        assert p1_league2.nickname.value == "aime"


# ---------------------------------------------------------------------------
# v3: register_players_and_pair under one_pair_per_player=False
# ---------------------------------------------------------------------------


class TestRegisterPlayersAndPairOTPPFalse:
    def test_player_can_join_second_pair_when_otpp_false(self) -> None:
        league = _league_otpp_false()
        _, pair_ab = league.register_players_and_pair("alice", "bob")
        new_players, pair_ac = league.register_players_and_pair("alice", "charlie")

        assert pair_ab.pair_id != pair_ac.pair_id
        assert len(league.pairs) == 2
        assert len(new_players) == 1
        assert new_players[0].nickname.value == "charlie"

    def test_player_on_three_pairs_when_otpp_false(self) -> None:
        league = _league_otpp_false()
        league.register_players_and_pair("alice", "bob")
        league.register_players_and_pair("alice", "charlie")
        league.register_players_and_pair("alice", "diana")

        assert len(league.pairs) == 3
        nicknames = [p.nickname.value for p in league.players]
        assert nicknames.count("alice") == 1
        assert {"alice", "bob", "charlie", "diana"} == set(nicknames)

    def test_otpp_true_still_rejects_second_pair_for_same_player(self) -> None:
        """Regression: OTPP=true is still the default for new leagues."""
        league = _league()
        league.register_players_and_pair("alice", "bob")
        with pytest.raises(PairConflictError):
            league.register_players_and_pair("alice", "charlie")


# ---------------------------------------------------------------------------
# League.edit_player_nickname
# ---------------------------------------------------------------------------


class TestEditPlayerNickname:
    def _league_with_players(self) -> League:
        league = _league()
        league.register_players_and_pair("alice", "bob")
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

    def test_update_player_rating_sets_rating(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")

        updated = league.update_player_rating(str(alice.player_id.value), 3.5)

        assert updated.rating == 3.5

    def test_update_player_rating_can_clear_rating(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.update_player_rating(str(alice.player_id.value), 3.5)

        updated = league.update_player_rating(str(alice.player_id.value), None)

        assert updated.rating is None

    def test_update_player_rating_rejects_negative_rating(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")

        with pytest.raises(InvalidPlayerRatingError):
            league.update_player_rating(str(alice.player_id.value), -1.0)


# ---------------------------------------------------------------------------
# League player aliases
# ---------------------------------------------------------------------------


class TestPlayerAliases:
    def _league_with_players(self) -> League:
        league = _league()
        league.add_players(["alice", "bob", "charlie"])
        return league

    def _get_player(self, league: League, nickname: str):  # type: ignore[return]
        return next(p for p in league.players if p.has_nickname(PlayerNickname(nickname)))

    def test_add_alias_to_player(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")

        updated = league.add_alias_to_player(str(alice.player_id.value), "Ali")

        assert updated.canonical_nickname.value == "alice"
        assert [a.value for a in updated.aliases] == ["ali"]
        assert league._find_player_by_nickname(PlayerNickname("ali")) == alice

    def test_add_alias_rejects_collision_with_other_canonical(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")

        with pytest.raises(NicknameAlreadyInUseError):
            league.add_alias_to_player(str(alice.player_id.value), "bob")

    def test_add_alias_rejects_collision_with_other_alias(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        bob = self._get_player(league, "bob")
        league.add_alias_to_player(str(bob.player_id.value), "bobby")

        with pytest.raises(NicknameAlreadyInUseError):
            league.add_alias_to_player(str(alice.player_id.value), "BOBBY")

    def test_remove_alias_from_player(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.add_alias_to_player(str(alice.player_id.value), "ali")

        updated = league.remove_alias_from_player(str(alice.player_id.value), "ali")

        assert updated.aliases == []
        assert not updated.has_nickname(PlayerNickname("ali"))

    def test_remove_canonical_alias_raises(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")

        with pytest.raises(CannotRemoveCanonicalNicknameError):
            league.remove_alias_from_player(str(alice.player_id.value), "alice")

    def test_edit_to_existing_alias_promotes_alias_and_discards_old_canonical(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.add_alias_to_player(str(alice.player_id.value), "ali")

        updated = league.edit_player_nickname(str(alice.player_id.value), "ali")

        assert updated.canonical_nickname.value == "ali"
        assert updated.aliases == []
        assert not updated.has_nickname(PlayerNickname("alice"))

    def test_add_players_rejects_collision_against_alias(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.add_alias_to_player(str(alice.player_id.value), "ali")

        with pytest.raises(NicknameAlreadyInUseError):
            league.add_players(["ALI"])

    def test_same_player_with_two_aliases_on_one_pair_raises(self) -> None:
        league = self._league_with_players()
        alice = self._get_player(league, "alice")
        league.add_alias_to_player(str(alice.player_id.value), "ali")

        with pytest.raises(SamePlayerWithinSinglePairError):
            league.register_players_and_pair("alice", "ali")

    def test_same_player_via_aliases_on_both_pairs_raises(self) -> None:
        league = _league_otpp_false()
        league.add_players(["alice", "bob", "charlie"])
        alice = self._get_player(league, "alice")
        league.add_alias_to_player(str(alice.player_id.value), "ali")

        _, pair1 = league.register_players_and_pair("ali", "bob")
        _, pair2 = league.register_players_and_pair("alice", "charlie")

        with pytest.raises(SamePlayerOnBothPairsError):
            league.validate_pairs_do_not_share_players(pair1, pair2)


# ---------------------------------------------------------------------------
# League.delete_pair
# ---------------------------------------------------------------------------


class TestDeletePair:
    def test_deletes_pair_successfully(self) -> None:
        league = _league()
        _, pair = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair.pair_id.value))
        assert len(league.pairs) == 0

    def test_players_remain_after_pair_deletion(self) -> None:
        league = _league()
        _, pair = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair.pair_id.value))
        assert len(league.players) == 2

    def test_deleted_pair_id_added_to_pending_list(self) -> None:
        league = _league()
        _, pair = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair.pair_id.value))
        assert pair.pair_id in league.pending_deleted_pair_ids

    def test_pair_not_found_raises(self) -> None:
        league = _league()
        with pytest.raises(PairNotFoundError):
            league.delete_pair(str(uuid.uuid4()))

    def test_deletes_only_specified_pair(self) -> None:
        league = _league()
        _, pair1 = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair1.pair_id.value))
        _, pair2 = league.register_players_and_pair("charlie", "diana")
        assert len(league.pairs) == 1
        assert league.pairs[0].pair_id == pair2.pair_id

    def test_delete_already_deleted_pair_raises(self) -> None:
        league = _league()
        _, pair = league.register_players_and_pair("alice", "bob")
        league.delete_pair(str(pair.pair_id.value))
        with pytest.raises(PairNotFoundError):
            league.delete_pair(str(pair.pair_id.value))


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

    def test_adds_single_nickname_with_rating(self) -> None:
        league = _league()
        added = league.add_players(["alex"], ratings=[3.5])
        assert len(added) == 1
        assert added[0].nickname.value == "alex"
        assert added[0].rating == 3.5

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
        league.add_players(["Alex-Kim", "DANIEL"])
        nicks = {p.nickname.value for p in league.players}
        assert nicks == {"alex-kim", "daniel"}

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

    def test_ratings_length_must_match_nicknames(self) -> None:
        league = _league()
        with pytest.raises(ValueError):
            league.add_players(["alex"], ratings=[])

    def test_add_players_rejects_negative_rating(self) -> None:
        league = _league()
        with pytest.raises(InvalidPlayerRatingError):
            league.add_players(["alex"], ratings=[-1.0])

    def test_add_players_does_not_create_pairs(self) -> None:
        """Pairs are still created only inside register_players_and_pair."""
        league = _league()
        league.add_players(["alex", "daniel"])
        assert league.pairs == []

    def test_pre_registered_player_is_reused_by_match_submission(self) -> None:
        """When a host pre-registers a player and that player later submits a
        match, register_players_and_pair finds the existing Player rather
        than creating a duplicate."""
        league = _league()
        added = league.add_players(["alex", "daniel"])
        before_ids = {p.player_id for p in league.players}

        new_players, _ = league.register_players_and_pair("alex", "daniel")

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

    def test_rejects_player_with_pair_membership(self) -> None:
        league = _league()
        league.register_players_and_pair("alex", "daniel")
        alex = next(p for p in league.players if p.nickname.value == "alex")

        with pytest.raises(PlayerHasParticipationError) as exc:
            league.remove_player(str(alex.player_id.value))

        assert exc.value.pairs_count == 1
        assert exc.value.matches_count == 0
        assert {p.nickname.value for p in league.players} == {"alex", "daniel"}

    def test_rejects_player_with_match_participation(self) -> None:
        """Even when the pair is gone but match_count was loaded by the repo
        as > 0 (defensive — in practice the FK keeps the pair alive), the
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
        league.register_players_and_pair("alex", "daniel")
        alex = next(p for p in league.players if p.nickname.value == "alex")

        with pytest.raises(PlayerHasParticipationError) as exc:
            league.remove_player(str(alex.player_id.value))

        assert exc.value.player_id == str(alex.player_id.value)

    def test_does_not_add_to_pending_when_guard_blocks(self) -> None:
        league = _league()
        league.register_players_and_pair("alex", "daniel")
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
