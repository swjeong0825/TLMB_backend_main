"""Unit tests for LeagueRules (v3)."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import InvalidLeagueRulesError


# ---------------------------------------------------------------------------
# v3 round-trip and v1/v2 upgrade
# ---------------------------------------------------------------------------


def test_from_dict_v3_round_trip() -> None:
    raw = {
        "version": 3,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw)
    assert rules.to_dict() == raw


def test_from_dict_v1_input_is_upgraded_to_v3_with_defaults() -> None:
    raw_v1 = {
        "version": 1,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
    }
    rules = LeagueRules.from_dict(raw_v1)
    assert rules.version == 3
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.to_dict() == {
        "version": 3,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won"],
    }


def test_from_dict_v1_input_with_otpp_false_upgrades_to_v3() -> None:
    """v3 unlocks OTPP=false. A v1 input carrying OTPP=false is upgraded.

    v1 has no `ranking_subject` field, so the default `"team"` is injected;
    `(team, OTPP=false)` does not violate the v3 cross-rule.
    """
    rules = LeagueRules.from_dict(
        {
            "version": 1,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
        }
    )
    assert rules.version == 3
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)


def test_from_dict_v2_input_upgrades_to_v3() -> None:
    raw_v2 = {
        "version": 2,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw_v2)
    assert rules.version == 3
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won", "games_diff")


def test_from_dict_ignores_unknown_keys() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "future_field": 123,
        }
    )
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True


def test_default_for_new_league_is_v3() -> None:
    rules = LeagueRules.default_for_new_league()
    assert rules.version == 3
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True
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
        {"version": 4, "match_pair_idempotency": "none", "one_team_per_player": True},
    ],
)
def test_from_dict_rejects_legacy_invalid(bad: dict) -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(bad)


def test_from_dict_rejects_unknown_ranking_subject() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 3,
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
                "version": 3,
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
                "version": 3,
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
                "version": 3,
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
                "version": 3,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won", "matches_won"],
            }
        )


# ---------------------------------------------------------------------------
# v3 cross-rule and OTPP=false acceptance
# ---------------------------------------------------------------------------


def test_from_dict_accepts_team_subject_with_otpp_false() -> None:
    """v3 unlocks `(team, OTPP=false)` — players on multiple teams with team-rank."""
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 3
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"


def test_from_dict_accepts_player_subject_with_otpp_false() -> None:
    """v3 unlocks `(player, OTPP=false)` — the cross-rule's only player-subject combo."""
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 3
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "player"


def test_from_dict_rejects_player_subject_with_otpp_true() -> None:
    """v3 cross-rule: `ranking_subject='player'` requires `one_team_per_player=false`.

    The combo `(player, OTPP=true)` is mathematically equivalent to
    `(team, OTPP=true)` and therefore conveys no distinct information; v3
    rejects it on input. Existing prod rows with this shape are auto-rewritten
    by alembic 004.
    """
    with pytest.raises(InvalidLeagueRulesError) as exc:
        LeagueRules.from_dict(
            {
                "version": 3,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )
    # Message should mention both combinations the user could pick instead.
    msg = str(exc.value)
    assert "ranking_subject" in msg
    assert "one_team_per_player" in msg


def test_from_dict_v2_input_with_player_subject_and_otpp_true_is_rejected() -> None:
    """A v2-shaped input that violates the v3 cross-rule is rejected on read.

    In production this code path never fires because alembic 004 rewrites all
    such rows before any upgrade-on-read happens, but the validation must still
    be uniform: any input shape that violates the cross-rule is rejected,
    regardless of declared `version`.
    """
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 2,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )
