"""Unit tests for domain value objects.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import uuid

import pytest

from app.domain.aggregates.league.value_objects import (
    HostToken,
    LeagueId,
    PlayerId,
    PlayerNickname,
    TeamId,
)
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import InvalidSetScoreError


# ---------------------------------------------------------------------------
# LeagueId
# ---------------------------------------------------------------------------


class TestLeagueId:
    def test_generate_produces_valid_uuid(self) -> None:
        lid = LeagueId.generate()
        assert isinstance(lid.value, uuid.UUID)

    def test_two_generated_ids_are_distinct(self) -> None:
        assert LeagueId.generate() != LeagueId.generate()

    def test_from_str_round_trip(self) -> None:
        raw = str(uuid.uuid4())
        lid = LeagueId.from_str(raw)
        assert str(lid) == raw

    def test_from_str_invalid_uuid_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            LeagueId.from_str("not-a-uuid")

    def test_equality_same_value(self) -> None:
        raw = str(uuid.uuid4())
        assert LeagueId.from_str(raw) == LeagueId.from_str(raw)

    def test_inequality_different_values(self) -> None:
        assert LeagueId.generate() != LeagueId.generate()


# ---------------------------------------------------------------------------
# HostToken
# ---------------------------------------------------------------------------


class TestHostToken:
    def test_str_returns_value(self) -> None:
        token = HostToken(value="secret-token")
        assert str(token) == "secret-token"

    def test_equality(self) -> None:
        assert HostToken(value="abc") == HostToken(value="abc")

    def test_inequality(self) -> None:
        assert HostToken(value="abc") != HostToken(value="xyz")

    def test_is_immutable(self) -> None:
        token = HostToken(value="original")
        with pytest.raises((AttributeError, TypeError)):
            token.value = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PlayerId
# ---------------------------------------------------------------------------


class TestPlayerId:
    def test_generate_produces_valid_uuid(self) -> None:
        pid = PlayerId.generate()
        assert isinstance(pid.value, uuid.UUID)

    def test_two_generated_ids_are_distinct(self) -> None:
        assert PlayerId.generate() != PlayerId.generate()

    def test_from_str_round_trip(self) -> None:
        raw = str(uuid.uuid4())
        pid = PlayerId.from_str(raw)
        assert str(pid) == raw

    def test_from_str_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            PlayerId.from_str("bad-uuid-here")


# ---------------------------------------------------------------------------
# PlayerNickname
# ---------------------------------------------------------------------------


class TestPlayerNickname:
    def test_stores_value_lowercased(self) -> None:
        nick = PlayerNickname("Alice")
        assert nick.value == "alice"

    def test_strips_surrounding_whitespace(self) -> None:
        nick = PlayerNickname("  Bob  ")
        assert nick.value == "bob"

    def test_empty_string_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            PlayerNickname("")

    def test_whitespace_only_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            PlayerNickname("   ")

    def test_equality_is_case_insensitive(self) -> None:
        assert PlayerNickname("Alice") == PlayerNickname("alice")
        assert PlayerNickname("BOB") == PlayerNickname("bob")

    def test_different_nicknames_are_not_equal(self) -> None:
        assert PlayerNickname("alice") != PlayerNickname("bob")

    def test_str_returns_lowercased_value(self) -> None:
        assert str(PlayerNickname("Charlie")) == "charlie"

    def test_is_immutable(self) -> None:
        nick = PlayerNickname("alice")
        with pytest.raises((AttributeError, TypeError)):
            nick.value = "bob"  # type: ignore[misc]

    def test_mixed_case_normalized(self) -> None:
        nick = PlayerNickname("AlIcE")
        assert nick.value == "alice"


# ---------------------------------------------------------------------------
# TeamId
# ---------------------------------------------------------------------------


class TestTeamId:
    def test_generate_produces_valid_uuid(self) -> None:
        tid = TeamId.generate()
        assert isinstance(tid.value, uuid.UUID)

    def test_two_generated_ids_are_distinct(self) -> None:
        assert TeamId.generate() != TeamId.generate()

    def test_from_str_round_trip(self) -> None:
        raw = str(uuid.uuid4())
        tid = TeamId.from_str(raw)
        assert str(tid) == raw

    def test_from_str_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            TeamId.from_str("not-a-uuid")


# ---------------------------------------------------------------------------
# MatchId
# ---------------------------------------------------------------------------


class TestMatchId:
    def test_generate_produces_valid_uuid(self) -> None:
        mid = MatchId.generate()
        assert isinstance(mid.value, uuid.UUID)

    def test_two_generated_ids_are_distinct(self) -> None:
        assert MatchId.generate() != MatchId.generate()

    def test_from_str_round_trip(self) -> None:
        raw = str(uuid.uuid4())
        mid = MatchId.from_str(raw)
        assert str(mid) == raw


# ---------------------------------------------------------------------------
# SetScore
# ---------------------------------------------------------------------------


class TestSetScore:
    def test_valid_non_zero_scores_accepted(self) -> None:
        s = SetScore(team1_score="6", team2_score="3")
        assert s.team1_score == "6"
        assert s.team2_score == "3"

    def test_zero_scores_are_valid(self) -> None:
        s = SetScore(team1_score="0", team2_score="0")
        assert s.team1_score == "0"
        assert s.team2_score == "0"

    def test_large_scores_are_valid(self) -> None:
        s = SetScore(team1_score="100", team2_score="99")
        assert s.team1_score == "100"

    def test_negative_team1_score_raises(self) -> None:
        with pytest.raises(InvalidSetScoreError):
            SetScore(team1_score="-1", team2_score="6")

    def test_negative_team2_score_raises(self) -> None:
        with pytest.raises(InvalidSetScoreError):
            SetScore(team1_score="6", team2_score="-1")

    def test_non_integer_team1_score_raises(self) -> None:
        with pytest.raises(InvalidSetScoreError):
            SetScore(team1_score="abc", team2_score="6")

    def test_non_integer_team2_score_raises(self) -> None:
        with pytest.raises(InvalidSetScoreError):
            SetScore(team1_score="6", team2_score="xyz")

    def test_float_string_raises(self) -> None:
        with pytest.raises(InvalidSetScoreError):
            SetScore(team1_score="6.5", team2_score="3")

    def test_winner_side_team1_wins(self) -> None:
        assert SetScore(team1_score="6", team2_score="3").winner_side() == "team1"

    def test_winner_side_team2_wins(self) -> None:
        assert SetScore(team1_score="2", team2_score="6").winner_side() == "team2"

    def test_winner_side_draw(self) -> None:
        assert SetScore(team1_score="6", team2_score="6").winner_side() == "draw"

    def test_zero_zero_is_draw(self) -> None:
        assert SetScore(team1_score="0", team2_score="0").winner_side() == "draw"

    def test_immutable(self) -> None:
        s = SetScore(team1_score="6", team2_score="3")
        with pytest.raises((AttributeError, TypeError)):
            s.team1_score = "7"  # type: ignore[misc]
