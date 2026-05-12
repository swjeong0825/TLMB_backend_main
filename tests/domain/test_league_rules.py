"""Unit tests for LeagueRules (v4)."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import InvalidLeagueRulesError


# ---------------------------------------------------------------------------
# v4 round-trip and v1/v2/v3 upgrade
# ---------------------------------------------------------------------------


def test_from_dict_v4_round_trip() -> None:
    raw = {
        "version": 4,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "require_eligible_players": True,
    }
    rules = LeagueRules.from_dict(raw)
    assert rules.to_dict() == raw


def test_from_dict_v3_round_trip_upgrades_to_v4_with_default_flag() -> None:
    """v3 inputs are accepted and upgraded transparently to v4 with
    require_eligible_players=False (preserves prior behavior byte-for-byte)."""
    raw_v3 = {
        "version": 3,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw_v3)
    assert rules.version == 4
    assert rules.require_eligible_players is False
    assert rules.to_dict() == {
        "version": 4,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
        "require_eligible_players": False,
    }


def test_from_dict_v1_input_is_upgraded_to_v4_with_defaults() -> None:
    raw_v1 = {
        "version": 1,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
    }
    rules = LeagueRules.from_dict(raw_v1)
    assert rules.version == 4
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.require_eligible_players is False
    assert rules.to_dict() == {
        "version": 4,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won"],
        "require_eligible_players": False,
    }


def test_from_dict_v1_input_with_otpp_false_upgrades_to_v4() -> None:
    """v3 unlocked OTPP=false; v4 keeps it. A v1 input carrying OTPP=false
    upgrades cleanly, defaulting `require_eligible_players=False`."""
    rules = LeagueRules.from_dict(
        {
            "version": 1,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
        }
    )
    assert rules.version == 4
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.require_eligible_players is False


def test_from_dict_v2_input_upgrades_to_v4() -> None:
    raw_v2 = {
        "version": 2,
        "match_pair_idempotency": "once_per_league",
        "one_team_per_player": True,
        "ranking_subject": "team",
        "tie_breakers": ["matches_won", "games_diff"],
    }
    rules = LeagueRules.from_dict(raw_v2)
    assert rules.version == 4
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won", "games_diff")
    assert rules.require_eligible_players is False


def test_from_dict_ignores_unknown_keys() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": False,
            "future_field": 123,
        }
    )
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True


def test_default_for_new_league_is_v4_with_eligibility_off() -> None:
    rules = LeagueRules.default_for_new_league()
    assert rules.version == 4
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is True
    assert rules.ranking_subject == "team"
    assert rules.tie_breakers == ("matches_won",)
    assert rules.require_eligible_players is False


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
        # version 5 is not yet supported.
        {"version": 5, "match_pair_idempotency": "none", "one_team_per_player": True},
    ],
)
def test_from_dict_rejects_legacy_invalid(bad: dict) -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(bad)


def test_from_dict_rejects_unknown_ranking_subject() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 4,
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
                "version": 4,
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
                "version": 4,
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
                "version": 4,
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
                "version": 4,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won", "matches_won"],
            }
        )


# ---------------------------------------------------------------------------
# v3 cross-rule and OTPP=false acceptance (preserved verbatim under v4)
# ---------------------------------------------------------------------------


def test_from_dict_accepts_team_subject_with_otpp_false() -> None:
    """v3 unlocks `(team, OTPP=false)` — players on multiple teams with team-rank."""
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 4
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "team"


def test_from_dict_accepts_player_subject_with_otpp_false() -> None:
    """v3 unlocks `(player, OTPP=false)` — the cross-rule's only player-subject combo."""
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "ranking_subject": "player",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.version == 4
    assert rules.one_team_per_player is False
    assert rules.ranking_subject == "player"


def test_from_dict_rejects_player_subject_with_otpp_true() -> None:
    """v3 cross-rule (still enforced under v4): `ranking_subject='player'`
    requires `one_team_per_player=false`."""
    with pytest.raises(InvalidLeagueRulesError) as exc:
        LeagueRules.from_dict(
            {
                "version": 4,
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
    even when the declared version is older than v4."""
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
# v4 require_eligible_players parsing
# ---------------------------------------------------------------------------


def test_from_dict_v4_require_eligible_players_true() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
    )
    assert rules.require_eligible_players is True


def test_from_dict_v4_require_eligible_players_omitted_defaults_false() -> None:
    """v4 input without the new key still parses (forward compat one direction
    too — v4 client may have written the row before code knew to set it)."""
    rules = LeagueRules.from_dict(
        {
            "version": 4,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
        }
    )
    assert rules.require_eligible_players is False


def test_from_dict_v3_input_with_require_eligible_players_carries_flag_through() -> None:
    """Even though `require_eligible_players` is a v4 concept, an early-adopter
    client that sets it on a v3-shaped dict has its choice respected (the
    upgrade path picks the value up)."""
    rules = LeagueRules.from_dict(
        {
            "version": 3,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": True,
            "ranking_subject": "team",
            "tie_breakers": ["matches_won"],
            "require_eligible_players": True,
        }
    )
    assert rules.version == 4
    assert rules.require_eligible_players is True


def test_from_dict_rejects_non_boolean_require_eligible_players() -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(
            {
                "version": 4,
                "match_pair_idempotency": "once_per_league",
                "one_team_per_player": True,
                "ranking_subject": "team",
                "tie_breakers": ["matches_won"],
                "require_eligible_players": "yes",
            }
        )
