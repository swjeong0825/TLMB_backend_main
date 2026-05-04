"""Unit tests for LeagueRules."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import InvalidLeagueRulesError


# ---------------------------------------------------------------------------
# v2 round-trip and v1 upgrade
# ---------------------------------------------------------------------------


def test_from_dict_v2_round_trip() -> None:
    raw = {
        "version": 2,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw)
    assert rules.to_dict() == raw


def test_from_dict_v1_input_is_upgraded_to_v2_with_defaults() -> None:
    raw_v1 = {
        "version": 1,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
    }
    rules = LeagueRules.from_dict(raw_v1)
    assert rules.version == 2
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.to_dict() == {
        "version": 2,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won"],
    }


def test_from_dict_v1_input_with_otpp_false_is_rejected() -> None:
    """v2 locks one_team_per_player to true.

    v1 payloads carrying OTPP=false are rejected on read rather than silently
    upgraded. TODO(v3-ranking-tightening): when v3 unlocks OTPP=false, this
    test should flip back to expect a successful upgrade. See design doc 17.
    """
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 1,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
            }
        )


def test_from_dict_ignores_unknown_keys() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "future_field": 123,
        }
    )
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True


def test_default_for_new_league_matches_v1_behavior() -> None:
    rules = LeagueRules.default_for_new_league()
    assert rules.version == 2
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"version": 1},
        {"version": 1, "match_pair_idempotency": "once_per_day"},
        {"version": 1, "match_pair_idempotency": "none", "one_team_per_player": "yes"},
        {"version": 3, "match_pair_idempotency": "none", "one_team_per_player": True},
    ],
)
def test_from_dict_rejects_legacy_invalid(bad: dict) -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(bad)


def test_from_dict_rejects_unknown_ranking_subject() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "league",
                "tie_breakers": ["matches_won"],
            }
        )


def test_from_dict_rejects_unknown_metric() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won", "head_to_head"],
            }
        )


def test_from_dict_rejects_empty_tie_breakers() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": [],
            }
        )


def test_from_dict_rejects_non_list_tie_breakers() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": "matches_won",
            }
        )


def test_from_dict_rejects_duplicate_metric() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won", "matches_won"],
            }
        )


def test_from_dict_rejects_otpp_false_with_team_subject() -> None:
    """v2 locks one_team_per_player to true regardless of ranking_subject.

    TODO(v3-ranking-tightening): when v3 unlocks OTPP=false, (team, OTPP=false)
    becomes legal and this test should flip to expect success. See design doc
    17 §"Forward-compatibility note".
    """
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
            }
        )


def test_from_dict_rejects_otpp_false_with_player_subject() -> None:
    """v2 locks one_team_per_player to true regardless of ranking_subject.

    There is no `(ranking_subject, OTPP)` cross-rule in v2; this case is
    rejected purely because OTPP=false is itself illegal. v3 will introduce a
    cross-rule that rejects (player, OTPP=true), at which point this combo
    `(player, OTPP=false)` becomes the legal one.
    """
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": False,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )


def test_from_dict_accepts_player_subject_with_otpp_true() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 2,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.ranking_subject == "player"
