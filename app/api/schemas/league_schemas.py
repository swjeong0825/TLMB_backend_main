from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator


class LeagueRulesV1Request(BaseModel):
    """Shape of `rules` on create-league; `version` is validated in the domain (LeagueRules)."""

    version: int
    match_pair_idempotency: Literal["none", "once_per_league"]
    one_team_per_player: bool = True


class CreateLeagueRequest(BaseModel):
    title: str
    description: str | None = None
    rules: LeagueRulesV1Request | None = None

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title must not be blank")
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
    rank: int
    team_id: str
    player1_nickname: str
    player2_nickname: str
    wins: int
    losses: int


class GetStandingsResponse(BaseModel):
    standings: list[StandingsEntrySchema]


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
    players: list[PlayerEntrySchema]
    teams: list[TeamEntrySchema]
