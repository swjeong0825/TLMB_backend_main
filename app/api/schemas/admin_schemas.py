from __future__ import annotations

from pydantic import BaseModel, field_validator


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
