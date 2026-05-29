"""Shared LeagueRules presets for integration tests."""

from __future__ import annotations

from app.domain.aggregates.league.league_rules import LeagueRules

# Matches pre-rules behavior: multiple matches allowed for the same pair matchup.
LEAGUE_RULES_ALLOW_DUPLICATE_PAIR_MATCHUPS = LeagueRules.from_dict(
    {
        "version": 8,
        "pair_matchup_idempotency": "none",
        "one_pair_per_player": True,
        "ranking_subject": "pair",
        "tie_breakers": ["matches_won"],
        "auto_register_players_on_match": True,
    }
)
