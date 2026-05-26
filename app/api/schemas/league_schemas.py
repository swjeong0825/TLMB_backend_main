from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


RankingMetricLiteral = Literal[
    "matches_won",
    "match_diff",
    "games_won",
    "games_lost",
    "games_diff",
    "win_pct",
]


MatchPairIdempotencyLiteral = Literal["none", "once_per_league", "once_per_day"]


class LeagueRulesV7Request(BaseModel):
    """Shape of `rules` on create-league.

    `version` accepts 1 through 7: v1..v6 inputs
    are upgraded transparently in `LeagueRules.from_dict` — v5's
    `require_allowlist` is replaced by v6's
    `auto_register_players_on_match` with the boolean inverted (the new
    flag is the opposite framing), and v7 adds `once_per_day`.

    `auto_register_players_on_match` (default `true`) controls whether
    submitting a match with an unknown nickname auto-creates the `Player`
    row. When `false`, only pre-registered players can play; matches
    with unknown nicknames are rejected with
    `RosterMembershipRequiredError`.

    The v3 cross-rule (`(player, OTPP=true)` is rejected) is preserved.
    """

    version: Literal[1, 2, 3, 4, 5, 6, 7]
    match_pair_idempotency: MatchPairIdempotencyLiteral
    one_team_per_player: bool = True
    ranking_subject: Literal["team", "player"] | None = None
    tie_breakers: list[RankingMetricLiteral] | None = None
    auto_register_players_on_match: bool = True


LeagueRulesV6Request = LeagueRulesV7Request
LeagueRulesV5Request = LeagueRulesV7Request
LeagueRulesV4Request = LeagueRulesV7Request
LeagueRulesV3Request = LeagueRulesV7Request


class CreateLeagueRequest(BaseModel):
    """Body for `POST /leagues`.

    `host_email` is mandatory contact for the league host. Pydantic
    `EmailStr` rejects malformed addresses with 422 at the API edge;
    player-facing GET responses omit this field; admin read via
    `GET /admin/leagues/{league_id}` with `X-Host-Token`.

    `initial_players` is an optional bootstrap list — when non-empty the
    nicknames are inserted into the league's roster as `Player` rows as
    part of the same DB transaction that creates the league row. The
    list may be present even when `rules.auto_register_players_on_match`
    is `true` (the roster is still pre-populated, it just isn't enforced
    on match submission). Entries must be non-blank strings; the
    aggregate handles in-batch / against-existing duplicate detection
    and raises domain errors that map to 409.
    """

    title: str
    host_email: EmailStr
    description: str | None = None
    league_timezone: str = "America/Los_Angeles"
    rules: LeagueRulesV7Request | None = None
    initial_players: list[str] = []

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be blank")
        return v

    @field_validator("initial_players")
    @classmethod
    def initial_players_must_be_non_blank(cls, v: list[str]) -> list[str]:
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("initial_players entries must be non-blank strings")
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
    """Response for `POST /leagues/{id}/matches`.

    `created_at` is the DB-authoritative server timestamp at which the
    match row was inserted. The frontend uses it to compute the
    player-edit window from a known-good clock (instead of `Date.now()`
    on the client, which is unreliable in the presence of clock skew
    across devices).
    """

    match_id: str
    created_at: datetime


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
    draws: int = 0
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
    aliases: list[str] = Field(default_factory=list)
    rating: float | None = None
    teams_count: int = 0
    matches_count: int = 0


class TeamEntrySchema(BaseModel):
    team_id: str
    player1_nickname: str
    player2_nickname: str


class LeagueRulesResponseSchema(BaseModel):
    """Read-side projection of `LeagueRules` returned alongside league metadata.

    Mirrors `LeagueRules.to_dict()` so the frontend can render and gate UI on
    the active rule configuration without an additional round-trip. v7 is
    the canonical response version (older inputs are upgraded by
    `LeagueRules.from_dict` before they are returned).
    """

    version: int
    match_pair_idempotency: MatchPairIdempotencyLiteral
    one_team_per_player: bool
    ranking_subject: Literal["team", "player"]
    tie_breakers: list[RankingMetricLiteral]
    auto_register_players_on_match: bool


class GetLeagueRosterResponse(BaseModel):
    """Read-side projection of a league's roster + active rules.

    `player_score_edit_window_seconds` and
    `player_match_delete_window_seconds` are **server-wide config**
    (not per-league rules, not stored on the league row) — they are
    surfaced here so the frontend can fetch league title + rules +
    both values in the single roster trip it already makes on
    chat-page boot.

    - `player_score_edit_window_seconds` governs how long after
      `match.created_at` a non-admin caller can
      `PATCH /leagues/{league_id}/matches/{match_id}` to correct the
      score; admins (`X-Host-Token`) bypass the window entirely.
    - `player_match_delete_window_seconds` governs how long after
      `match.created_at` a non-admin caller can
      `DELETE /leagues/{league_id}/matches/{match_id}`; admins bypass
      the window. Tuned independently from the edit window because
      deletes are irreversible (default 600s vs 3600s for edits).
    """

    title: str
    league_timezone: str
    latest_match_date: date | None = None
    rules: LeagueRulesResponseSchema
    players: list[PlayerEntrySchema]
    teams: list[TeamEntrySchema]
    player_score_edit_window_seconds: int
    player_match_delete_window_seconds: int
