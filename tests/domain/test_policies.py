"""Unit tests for domain policies.

NicknameUniquenessPolicy, OneTeamPerPlayerPolicy and RosterMembershipPolicy
are pure in-memory objects; no database or async I/O is involved.
"""
from __future__ import annotations

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.policies import (
    NicknameUniquenessPolicy,
    OneTeamPerPlayerPolicy,
    RosterMembershipPolicy,
)
from app.domain.aggregates.league.value_objects import (
    PlayerId,
    PlayerNickname,
    TeamId,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _player(nickname: str) -> Player:
    return Player(player_id=PlayerId.generate(), nickname=PlayerNickname(nickname))


def _team(p1: Player, p2: Player) -> Team:
    return Team(team_id=TeamId.generate(), player_id_1=p1.player_id, player_id_2=p2.player_id)


# ---------------------------------------------------------------------------
# NicknameUniquenessPolicy
# ---------------------------------------------------------------------------


class TestNicknameUniquenessPolicy:
    def setup_method(self) -> None:
        self.policy = NicknameUniquenessPolicy()
        self.alice = _player("alice")
        self.bob = _player("bob")
        self.players = [self.alice, self.bob]

    def test_new_nickname_is_available(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("charlie"), self.players) is True

    def test_existing_nickname_is_not_available(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("alice"), self.players) is False

    def test_case_insensitive_collision_detected(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("ALICE"), self.players) is False

    def test_empty_player_list_always_available(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("alice"), []) is True

    def test_exclude_same_player_makes_nickname_available(self) -> None:
        result = self.policy.is_nickname_available(
            PlayerNickname("alice"),
            self.players,
            exclude_player_id=self.alice.player_id,
        )
        assert result is True

    def test_exclude_different_player_still_blocked(self) -> None:
        result = self.policy.is_nickname_available(
            PlayerNickname("alice"),
            self.players,
            exclude_player_id=self.bob.player_id,
        )
        assert result is False

    def test_exclude_none_behaves_like_no_exclusion(self) -> None:
        result = self.policy.is_nickname_available(
            PlayerNickname("alice"),
            self.players,
            exclude_player_id=None,
        )
        assert result is False

    def test_single_player_list_new_nickname_available(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("bob"), [self.alice]) is True

    def test_single_player_list_same_nickname_not_available(self) -> None:
        assert self.policy.is_nickname_available(PlayerNickname("alice"), [self.alice]) is False

    def test_alias_on_any_player_is_not_available(self) -> None:
        self.alice.nicknames.append(PlayerNickname("ali"))
        assert self.policy.is_nickname_available(PlayerNickname("ali"), self.players) is False

    def test_exclude_same_player_makes_alias_available_for_canonical_rename(self) -> None:
        self.alice.nicknames.append(PlayerNickname("ali"))
        result = self.policy.is_nickname_available(
            PlayerNickname("ali"),
            self.players,
            exclude_player_id=self.alice.player_id,
        )
        assert result is True


# ---------------------------------------------------------------------------
# OneTeamPerPlayerPolicy
# ---------------------------------------------------------------------------


class TestOneTeamPerPlayerPolicy:
    def setup_method(self) -> None:
        self.policy = OneTeamPerPlayerPolicy()
        self.alice = _player("alice")
        self.bob = _player("bob")
        self.charlie = _player("charlie")

    def test_player_with_no_teams_can_join(self) -> None:
        assert self.policy.can_join_team(self.alice.player_id, []) is True

    def test_player_already_on_team_cannot_join(self) -> None:
        team = _team(self.alice, self.bob)
        assert self.policy.can_join_team(self.alice.player_id, [team]) is False

    def test_second_player_on_team_also_blocked(self) -> None:
        team = _team(self.alice, self.bob)
        assert self.policy.can_join_team(self.bob.player_id, [team]) is False

    def test_unrelated_player_can_join(self) -> None:
        team = _team(self.alice, self.bob)
        assert self.policy.can_join_team(self.charlie.player_id, [team]) is True

    def test_exclude_own_team_id_allows_player(self) -> None:
        team = _team(self.alice, self.bob)
        result = self.policy.can_join_team(
            self.alice.player_id,
            [team],
            exclude_team_id=team.team_id,
        )
        assert result is True

    def test_exclude_different_team_id_still_blocks(self) -> None:
        team = _team(self.alice, self.bob)
        other_team = _team(self.charlie, _player("diana"))
        result = self.policy.can_join_team(
            self.alice.player_id,
            [team],
            exclude_team_id=other_team.team_id,
        )
        assert result is False

    def test_multiple_teams_player_blocked_if_on_any(self) -> None:
        team1 = _team(self.alice, self.bob)
        team2 = _team(self.charlie, _player("diana"))
        assert self.policy.can_join_team(self.alice.player_id, [team1, team2]) is False

    def test_multiple_teams_unrelated_player_can_join(self) -> None:
        team1 = _team(self.alice, self.bob)
        team2 = _team(self.charlie, _player("diana"))
        eve = _player("eve")
        assert self.policy.can_join_team(eve.player_id, [team1, team2]) is True


# ---------------------------------------------------------------------------
# RosterMembershipPolicy
# ---------------------------------------------------------------------------


class TestRosterMembershipPolicy:
    def setup_method(self) -> None:
        self.policy = RosterMembershipPolicy()

    def test_all_candidates_present_returns_empty_list(self) -> None:
        players = [_player("alice"), _player("bob")]
        candidates = [PlayerNickname("alice"), PlayerNickname("bob")]
        assert self.policy.find_missing_nicknames(candidates, players) == []

    def test_alias_satisfies_roster_membership(self) -> None:
        alice = _player("alice")
        alice.nicknames.append(PlayerNickname("ali"))
        players = [alice, _player("bob")]
        candidates = [PlayerNickname("ali"), PlayerNickname("bob")]
        assert self.policy.find_missing_nicknames(candidates, players) == []

    def test_partial_overlap_returns_only_missing(self) -> None:
        players = [_player("alice"), _player("bob")]
        candidates = [
            PlayerNickname("alice"),
            PlayerNickname("bob"),
            PlayerNickname("michael"),
            PlayerNickname("ryan"),
        ]
        assert self.policy.find_missing_nicknames(candidates, players) == [
            "michael",
            "ryan",
        ]

    def test_empty_roster_returns_all_candidates(self) -> None:
        candidates = [
            PlayerNickname("alice"),
            PlayerNickname("bob"),
            PlayerNickname("charlie"),
            PlayerNickname("diana"),
        ]
        assert self.policy.find_missing_nicknames(candidates, []) == [
            "alice",
            "bob",
            "charlie",
            "diana",
        ]

    def test_empty_candidates_returns_empty(self) -> None:
        players = [_player("alice"), _player("bob")]
        assert self.policy.find_missing_nicknames([], players) == []

    def test_dedupes_repeated_missing_in_input(self) -> None:
        """Same missing nickname appearing twice is reported once, in input
        order of first appearance."""
        players = [_player("alice")]
        candidates = [
            PlayerNickname("alice"),
            PlayerNickname("michael"),
            PlayerNickname("michael"),
            PlayerNickname("ryan"),
        ]
        assert self.policy.find_missing_nicknames(candidates, players) == [
            "michael",
            "ryan",
        ]

    def test_relies_on_value_object_normalization(self) -> None:
        """Policy compares on PlayerNickname.value, which is already normalized
        (lowercased + stripped) by the value object's constructor."""
        players = [_player("alice")]
        candidates = [PlayerNickname("ALICE "), PlayerNickname(" Bob")]
        assert self.policy.find_missing_nicknames(candidates, players) == ["bob"]

    def test_preserves_input_order_of_first_appearance(self) -> None:
        players: list[Player] = []
        candidates = [
            PlayerNickname("zed"),
            PlayerNickname("aime"),
            PlayerNickname("mike"),
        ]
        assert self.policy.find_missing_nicknames(candidates, players) == [
            "zed",
            "aime",
            "mike",
        ]

    def test_iterable_input_supported(self) -> None:
        """Signature accepts Iterable[PlayerNickname], not just list."""
        players = [_player("alice")]
        candidates = (PlayerNickname(n) for n in ["alice", "michael"])
        assert self.policy.find_missing_nicknames(candidates, players) == ["michael"]
