from __future__ import annotations

from pydantic import BaseModel, field_validator

from app.api.schemas.league_schemas import AllowlistEntrySchema


class EditPlayerNicknameRequest(BaseModel):
    new_nickname: str

    @field_validator("new_nickname")
    @classmethod
    def must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("new_nickname must not be blank")
        return v


class EditPlayerNicknameResponse(BaseModel):
    player_id: str
    new_nickname: str


class EditMatchScoreRequest(BaseModel):
    team1_score: str
    team2_score: str


class EditMatchScoreResponse(BaseModel):
    match_id: str
    team1_score: str
    team2_score: str


class AddAllowlistEntriesRequest(BaseModel):
    nicknames: list[str]

    @field_validator("nicknames")
    @classmethod
    def must_be_non_empty_and_no_blanks(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("nicknames must be a non-empty list")
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("nicknames entries must be non-blank strings")
        return v


class AddAllowlistEntriesResponse(BaseModel):
    allowlist: list[AllowlistEntrySchema]
