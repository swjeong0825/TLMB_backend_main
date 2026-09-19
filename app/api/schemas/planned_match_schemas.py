from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from app.domain.aggregates.planned_match.value_objects import PlannedMatchValue


class PlannedMatchSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    value: StrictStr

    @field_validator("value")
    @classmethod
    def valid_matchup(cls, value: str) -> str:
        return PlannedMatchValue(value).value


class UploadPlannedMatchesRequest(BaseModel):
    matches: list[PlannedMatchSchema] = Field(min_length=1)

    @field_validator("matches")
    @classmethod
    def unique_ids(cls, matches: list[PlannedMatchSchema]) -> list[PlannedMatchSchema]:
        if len({match.id for match in matches}) != len(matches):
            raise ValueError("Duplicate planned match IDs in the same request")
        return matches


class PlannedMatchesResponse(BaseModel):
    matches: list[PlannedMatchSchema]
