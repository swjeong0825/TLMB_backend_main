from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.schemas.league_schemas import PlayerEntrySchema


class EditPlayerNicknameRequest(BaseModel):
    new_nickname: str | None = None
    rating: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("new_nickname")
    @classmethod
    def must_not_be_blank(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("new_nickname must not be blank")
        return v

    @model_validator(mode="after")
    def must_include_at_least_one_field(self) -> "EditPlayerNicknameRequest":
        if "new_nickname" in self.model_fields_set and self.new_nickname is None:
            raise ValueError("new_nickname must not be null; omit it to leave unchanged")
        if (
            "new_nickname" not in self.model_fields_set
            and "rating" not in self.model_fields_set
        ):
            raise ValueError("At least one of new_nickname or rating must be supplied")
        return self


class EditPlayerNicknameResponse(BaseModel):
    player_id: str
    new_nickname: str
    rating: float | None = None


class EditMatchScoreRequest(BaseModel):
    pair1_score: str
    pair2_score: str


class EditMatchScoreResponse(BaseModel):
    match_id: str
    pair1_score: str
    pair2_score: str


class EditSinglesMatchScoreRequest(BaseModel):
    player1_score: str
    player2_score: str


class EditSinglesMatchScoreResponse(BaseModel):
    match_id: str
    player1_score: str
    player2_score: str


class AddPlayerInput(BaseModel):
    nickname: str
    rating: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("nickname")
    @classmethod
    def nickname_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("player nickname must not be blank")
        return v


class AddPlayersRequest(BaseModel):
    nicknames: list[str] | None = None
    players: list[AddPlayerInput] | None = None

    @field_validator("nicknames")
    @classmethod
    def must_be_non_empty_and_no_blanks(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        if not v:
            raise ValueError("nicknames must be a non-empty list")
        for entry in v:
            if not isinstance(entry, str) or not entry.strip():
                raise ValueError("nicknames entries must be non-blank strings")
        return v

    @field_validator("players")
    @classmethod
    def players_must_be_non_empty(
        cls, v: list[AddPlayerInput] | None
    ) -> list[AddPlayerInput] | None:
        if v is not None and not v:
            raise ValueError("players must be a non-empty list")
        return v

    @model_validator(mode="after")
    def must_use_one_payload_shape(self) -> "AddPlayersRequest":
        has_nicknames = self.nicknames is not None
        has_players = self.players is not None
        if has_nicknames == has_players:
            raise ValueError("Supply exactly one of nicknames or players")
        return self


class AddPlayersResponse(BaseModel):
    players: list[PlayerEntrySchema]


class AddPlayerAliasRequest(BaseModel):
    alias: str

    @field_validator("alias")
    @classmethod
    def alias_must_not_be_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("alias must not be blank")
        return v


class PlayerAliasResponse(BaseModel):
    player_id: str
    nickname: str
    aliases: list[str]


class GetLeagueAdminInfoResponse(BaseModel):
    host_email: str
