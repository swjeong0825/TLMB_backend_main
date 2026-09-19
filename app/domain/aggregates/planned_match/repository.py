from abc import ABC, abstractmethod

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch


class PlannedMatchRepository(ABC):
    @abstractmethod
    async def upsert_many(self, matches: list[PlannedMatch]) -> None: ...

    @abstractmethod
    async def get_all_by_league(self, league_id: LeagueId) -> list[PlannedMatch]:
        """Return plans ordered by ascending UUID."""
        ...
