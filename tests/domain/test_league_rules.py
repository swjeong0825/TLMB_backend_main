"""Unit tests for LeagueRules."""
from __future__ import annotations

import pytest

from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.exceptions import InvalidLeagueRulesError


def test_from_dict_round_trip() -> None:
    raw = {
        "version": 1,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
    }
    rules = LeagueRules.from_dict(raw)
    assert rules.to_dict() == raw


def test_from_dict_ignores_unknown_keys() -> None:
    rules = LeagueRules.from_dict(
        {
            "version": 1,
            "match_pair_idempotency": "once_per_league",
            "one_team_per_player": False,
            "future_field": 123,
        }
    )
    assert rules.match_pair_idempotency == "once_per_league"
    assert rules.one_team_per_player is False


@pytest.mark.parametrize(
    "bad",
    [
        {},
        {"version": 1},
        {"version": 1, "match_pair_idempotency": "once_per_day"},
        {"version": 1, "match_pair_idempotency": "none", "one_team_per_player": "yes"},
    ],
)
def test_from_dict_rejects_invalid(bad: dict) -> None:
    with pytest.raises(InvalidLeagueRulesError):
        LeagueRules.from_dict(bad)
