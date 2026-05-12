from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


RankingMetricLiteral = Literal[
    "matches_won",
    "match_diff",
    "games_won",
    "games_lost",
    "games_diff",
    "win_pct",
]


class LeagueRulesV4Request(BaseModel):
    """Shape of `rules` on create-league.

    `version` accepts 1, 2, 3, or 4: v1, v2, and v3 inputs are upgraded
    transparently in `LeagueRules.from_dict`. v4 adds the optional
    `require_eligible_players: bool` flag (default `false`) which gates
    match-submission rejection against the host-curated eligible-players
    allowlist; see
    `Design_Doc/TLMB_Design_doc/20_eligible_players.md`.

    The v3 cross-rule (`(player, OTPP=true)` is rejected) is preserved.
    The pydantic model accepts plain `bool` for `one_team_per_player` so
    the cross-rule rejection surfaces as the domain-level error code
    rather than a generic pydantic validation error.
    """

    version: Literal[1, 2, 3, 4]
    match_pair_idempotency: Literal["none", "once_per_league"]
    one_team_per_player: bool = True
    ranking_subject: Literal["team", "player"] | None = None
    tie_breakers: list[RankingMetricLiteral] | None = None
    require_eligible_players: bool = False


# Back-compat alias for any callers still importing the v3 name.
LeagueRulesV3Request = LeagueRulesV4Request


class CreateLeagueRequest(BaseModel):
    """Body for `POST /leagues`.

    `eligible_players` is an optional bootstrap list — when non-empty the
    nicknames are inserted into the league's eligible-players allowlist as
    part of the same DB transaction that creates the league row. The list
    may be present even when `rules.require_eligible_players` is False
    (the allowlist is still populated, it just isn't enforced on match
    submission). Validation mirrors `AddEligiblePlayersRequest`: entries
    must be non-blank strings; the aggregate handles in-batch / against-
    existing duplicate detection and raises domain errors that map to 409.
    """

    title: str
    description: str | None = None
    rules: LeagueRulesV4Request | None = None # has default
    eligible_players: list[str] = []

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be blank")
        return v

    @field_validator("eligible_players")
    @classmethod
    def eligible_player_nicknames_must_be_non_blank(cls, v: list[str]) -> list[str]:
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("eligible_players entries must be non-blank strings")
        return v


class CreateLeagueResponse(BaseModel):
    league_id: str
    host_token: str


class LeagueListItemSchema(BaseModel):
    league_id: str
    title: str


class SearchLeaguesResponse(BaseModel):
    leagues: list[LeagueListItemSchema]


class SubmitMatchResultRequest(BaseModel):
    team1_nicknames: list[str]
    team2_nicknames: list[str]
    team1_score: str
    team2_score: str

    @field_validator("team1_nicknames", "team2_nicknames")
    @classmethod
    def must_have_exactly_two(cls, v: list[str]) -> list[str]:
        if len(v) != 2:
            raise ValueError("Each team must have exactly 2 player nicknames")
        return v


class SubmitMatchResultResponse(BaseModel):
    match_id: str


class StandingsEntrySchema(BaseModel):
    """Polymorphic standings row.

    `subject_kind` discriminates which identifier/display fields are populated:
    - "team": team_id, player1_nickname, player2_nickname are present;
      player_id and nickname are None.
    - "player": player_id and nickname are present; team_id, player1_nickname,
      player2_nickname are None.

    Metric fields are populated for both variants.
    """

    subject_kind: Literal["team", "player"]
    rank: int
    matches_played: int
    wins: int
    losses: int
    games_won: int
    games_lost: int
    games_diff: int
    win_pct: float
    team_id: str | None = None
    player1_nickname: str | None = None
    player2_nickname: str | None = None
    player_id: str | None = None
    nickname: str | None = None


class GetStandingsResponse(BaseModel):
    """Standings list for a league, plus the league's ordered ranking metrics.

    `tie_breakers` mirrors `LeagueRules.tie_breakers` (see backend design doc 17):
    the first entry is the primary ranking metric, the rest are sequential
    tie-breakers. Clients render the displayed metric column ("Games won",
    "Games ±", "Win %", ...) from `tie_breakers[0]` so the standings table
    reflects the metric the league is actually ranked by.
    """

    standings: list[StandingsEntrySchema]
    tie_breakers: list[RankingMetricLiteral]


class MatchHistoryRecordSchema(BaseModel):
    match_id: str
    team1_player1_nickname: str
    team1_player2_nickname: str
    team2_player1_nickname: str
    team2_player2_nickname: str
    team1_score: str
    team2_score: str
    created_at: datetime | None


class GetMatchHistoryResponse(BaseModel):
    matches: list[MatchHistoryRecordSchema]


class PlayerEntrySchema(BaseModel):
    player_id: str
    nickname: str


class TeamEntrySchema(BaseModel):
    team_id: str
    player1_nickname: str
    player2_nickname: str


class GetLeagueRosterResponse(BaseModel):
    title: str
    players: list[PlayerEntrySchema]
    teams: list[TeamEntrySchema]


class EligiblePlayerEntrySchema(BaseModel):
    eligible_player_id: str
    nickname: str


class GetEligiblePlayersResponse(BaseModel):
    eligible_players: list[EligiblePlayerEntrySchema]
