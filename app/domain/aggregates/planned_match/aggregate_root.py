from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.value_objects import PlannedMatchValue


@dataclass(frozen=True)
class PlannedMatch:
    league_id: LeagueId
    id: UUID
    value: PlannedMatchValue

    @classmethod
    def create(cls, league_id: LeagueId, id: UUID, value: str) -> PlannedMatch:
        return cls(league_id=league_id, id=id, value=PlannedMatchValue(value))
