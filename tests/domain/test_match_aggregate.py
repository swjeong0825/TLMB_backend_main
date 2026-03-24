"""Unit tests for the Match aggregate root.

All tests are pure in-memory; no database or async I/O involved.
"""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.exceptions import SameTeamOnBothSidesError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score(t1: str = "6", t2: str = "3") -> SetScore:
    return SetScore(team1_score=t1, team2_score=t2)


def _make_match(t1_score: str = "6", t2_score: str = "3") -> Match:
    return Match.create(
        league_id=LeagueId.generate(),
        team1_id=TeamId.generate(),
        team2_id=TeamId.generate(),
        set_score=_score(t1_score, t2_score),
    )


# ---------------------------------------------------------------------------
# Match.create
# ---------------------------------------------------------------------------


class TestMatchCreate:
    def test_returns_match_instance(self) -> None:
        match = _make_match()
        assert isinstance(match, Match)

    def test_stores_league_id(self) -> None:
        league_id = LeagueId.generate()
        t1 = TeamId.generate()
        t2 = TeamId.generate()
        match = Match.create(league_id, t1, t2, _score())
        assert match.league_id == league_id

    def test_stores_team_ids(self) -> None:
        t1 = TeamId.generate()
        t2 = TeamId.generate()
        match = Match.create(LeagueId.generate(), t1, t2, _score())
        assert match.team1_id == t1
        assert match.team2_id == t2

    def test_stores_set_score(self) -> None:
        score = _score("7", "5")
        match = Match.create(LeagueId.generate(), TeamId.generate(), TeamId.generate(), score)
        assert match.set_score == score

    def test_generates_unique_match_id(self) -> None:
        m1 = _make_match()
        m2 = _make_match()
        assert m1.match_id != m2.match_id

    def test_created_at_is_none_by_default(self) -> None:
        match = _make_match()
        assert match.created_at is None

    def test_same_team_on_both_sides_raises(self) -> None:
        team_id = TeamId.generate()
        with pytest.raises(SameTeamOnBothSidesError):
            Match.create(LeagueId.generate(), team_id, team_id, _score())

    def test_different_team_ids_do_not_raise(self) -> None:
        match = Match.create(
            LeagueId.generate(), TeamId.generate(), TeamId.generate(), _score()
        )
        assert match is not None


# ---------------------------------------------------------------------------
# Match.edit_score
# ---------------------------------------------------------------------------


class TestMatchEditScore:
    def test_updates_set_score(self) -> None:
        match = _make_match("6", "3")
        new_score = SetScore(team1_score="4", team2_score="6")
        match.edit_score(new_score)
        assert match.set_score.team1_score == "4"
        assert match.set_score.team2_score == "6"

    def test_replaces_entire_set_score_object(self) -> None:
        match = _make_match()
        original_score = match.set_score
        new_score = SetScore(team1_score="0", team2_score="0")
        match.edit_score(new_score)
        assert match.set_score is not original_score

    def test_team_ids_unchanged_after_edit_score(self) -> None:
        t1 = TeamId.generate()
        t2 = TeamId.generate()
        match = Match.create(LeagueId.generate(), t1, t2, _score())
        match.edit_score(SetScore(team1_score="7", team2_score="6"))
        assert match.team1_id == t1
        assert match.team2_id == t2

    def test_edit_score_to_same_values_succeeds(self) -> None:
        match = _make_match("6", "3")
        match.edit_score(SetScore(team1_score="6", team2_score="3"))
        assert match.set_score.team1_score == "6"
        assert match.set_score.team2_score == "3"

    def test_multiple_edits_reflect_latest_score(self) -> None:
        match = _make_match("6", "3")
        match.edit_score(SetScore(team1_score="7", team2_score="5"))
        match.edit_score(SetScore(team1_score="6", team2_score="4"))
        assert match.set_score.team1_score == "6"
        assert match.set_score.team2_score == "4"
