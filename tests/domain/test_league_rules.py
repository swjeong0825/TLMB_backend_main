"""Unit tests for LeagueRules (v7)."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import InvalidLeagueRulesError


# ---------------------------------------------------------------------------
# v7 round-trip and v1/v2/v3/v4/v5/v6 upgrade
# ---------------------------------------------------------------------------


def test_from_dict_v7_round_trip() -> None:
    raw = {
        "version": 7,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "auto_register_players_on_match": False,
    }
    rules = LeagueRules.from_dict(raw)
    assert rules.to_dict() == raw


def test_from_dict_v5_round_trip_inverts_require_allowlist_to_v7() -> None:
    """v5 `require_allowlist=True` becomes v7 `auto_register_players_on_match=False`
    (boolean is inverted because the v6+ flag is the opposite framing)."""
    raw_v5 = {
        "version": 5,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "require_allowlist": True,
    }
    rules = LeagueRules.from_dict(raw_v5)
    assert rules.version == 7
    assert rules.auto_register_players_on_match is False
    assert rules.to_dict() == {
        "version": 7,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "auto_register_players_on_match": False,
    }


def test_from_dict_v5_require_allowlist_false_becomes_auto_register_true() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 5,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_allowlist": False,
        }
    )
    assert rules.version == 7
    assert rules.auto_register_players_on_match is True


def test_from_dict_v4_legacy_key_round_trip_upgrades_to_v7() -> None:
    """v4 `require_eligible_players=True` becomes v7 `auto_register_players_on_match=False`."""
    raw_v4 = {
        "version": 4,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "require_eligible_players": True,
    }
    rules = LeagueRules.from_dict(raw_v4)
    assert rules.version == 7
    assert rules.auto_register_players_on_match is False
    assert rules.to_dict() == {
        "version": 7,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "auto_register_players_on_match": False,
    }


def test_from_dict_v3_round_trip_upgrades_to_v7_with_default_flag() -> None:
    """v3 inputs are accepted and upgraded transparently to v7 with
    auto_register_players_on_match=True (default behavior preserved)."""
    raw_v3 = {
        "version": 3,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw_v3)
    assert rules.version == 7
    assert rules.auto_register_players_on_match is True
    assert rules.to_dict() == {
        "version": 7,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "auto_register_players_on_match": True,
    }


def test_from_dict_v1_input_is_upgraded_to_v7_with_defaults() -> None:
    raw_v1 = {
        "version": 1,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
    }
    rules = LeagueRules.from_dict(raw_v1)
    assert rules.version == 7
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.auto_register_players_on_match is True
    assert rules.to_dict() == {
        "version": 7,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won"],
        "auto_register_players_on_match": True,
    }


def test_from_dict_v1_input_with_otpp_false_upgrades_to_v7() -> None:
    """v3 unlocked OTPP=false; later versions keep it. A v1 input carrying
    OTPP=false upgrades cleanly, defaulting auto_register_players_on_match=True."""
    rules = LeagueRules.from_dict(
        {
            "version": 1,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
        }
    )
    assert rules.version == 7
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.auto_register_players_on_match is True


def test_from_dict_v2_input_upgrades_to_v7() -> None:
    raw_v2 = {
        "version": 2,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw_v2)
    assert rules.version == 7
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won", "games_diff")
    assert rules.auto_register_players_on_match is True


def test_from_dict_ignores_unknown_keys() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 7,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
            "future_field": 123,
        }
    )
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True


def test_from_dict_accepts_once_per_day() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 7,
            "match_pair_idempotency": "once_per_day",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "auto_register_players_on_match": True,
        }
    )
    assert rules.match_pair_idempotency == "once_per_day"


def test_default_for_new_league_is_v7_with_auto_register_on_and_once_per_day() -> None:
    rules = LeagueRules.default_for_new_league()
    assert rules.version == 7
    assert rules.match_pair_idempotency == "once_per_day"
    assert rules.one_team_per_player is True
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.auto_register_players_on_match is True


# ---------------------------------------------------------------------------
# Rejection cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"version": 1},
        {"version": 1, "match_pair_idempotency": "none", "one_team_per_player": "yes"},
        {"version": 8, "match_pair_idempotency": "none", "one_team_per_player": True},
    ],
)
def test_from_dict_rejects_legacy_invalid(bad: dict) -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(bad)


def test_from_dict_rejects_unknown_ranking_subject() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 6,
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
                "version": 6,
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
                "version": 6,
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
                "version": 6,
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
                "version": 6,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won", "matches_won"],
            }
        )


# ---------------------------------------------------------------------------
# v3 cross-rule and OTPP=false acceptance (preserved verbatim under v7)
# ---------------------------------------------------------------------------


def test_from_dict_accepts_team_subject_with_otpp_false() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 6,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 7
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"


def test_from_dict_accepts_player_subject_with_otpp_false() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 6,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 7
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "player"


def test_from_dict_rejects_player_subject_with_otpp_true() -> None:
    """v3 cross-rule (still enforced under v7): `ranking_subject='player'`
    requires `one_team_per_player=false`."""
    with pytest.raises(InvalidLeagueRulesError) as exc:
        LeagueRules.from_dict(
            {
                "version": 6,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "player",
                "tie_breakers": ["matches_won"],
            }
        )
    msg = str(exc.value)
    assert "ranking_subject" in msg
    assert "one_team_per_player" in msg


def test_from_dict_v2_input_with_player_subject_and_otpp_true_is_rejected() -> None:
    """A v2-shaped input that violates the v3 cross-rule is rejected on read,
    even when the declared version is older than v7."""
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


# ---------------------------------------------------------------------------
# v5 → v6 boolean inversion (the load-bearing migration behavior)
# ---------------------------------------------------------------------------


def test_from_dict_v6_auto_register_omitted_defaults_true() -> None:
    """v6 input without the key still parses (forward compat — defaults match
    the product default of `True`)."""
    rules = LeagueRules.from_dict(
        {
            "version": 6,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.auto_register_players_on_match is True


def test_from_dict_v4_with_require_eligible_players_false_upgrades_to_auto_register_true() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": False,
        }
    )
    assert rules.version == 7
    assert rules.auto_register_players_on_match is True


def test_from_dict_rejects_non_boolean_auto_register_players_on_match() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 6,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "auto_register_players_on_match": "yes",
            }
        )


def test_from_dict_rejects_non_boolean_require_allowlist() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 5,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_allowlist": "yes",
            }
        )
