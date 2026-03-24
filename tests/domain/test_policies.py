"""Unit tests for domain policies.

NicknameUniquenessPolicy and OneTeamPerPlayerPolicy are pure in-memory objects;
no database or async I/O is involved.
"""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.policies import NicknameUniquenessPolicy, OneTeamPerPlayerPolicy
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname, TeamId


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
