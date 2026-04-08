"""Shared LeagueRules presets for integration tests."""

from __future__ import annotations

from app.domain.aggregates.league.league_rules import LeagueRules

# Matches pre–league-rules behavior: multiple matches allowed for the same team pair.
LEAGUE_RULES_ALLOW_DUPLICATE_TEAM_PAIRS = LeagueRules.from_dict(
    {
        "version": 1,
        "match_pair_idempotency": "none",
        "one_team_per_player": True,
    }
)
