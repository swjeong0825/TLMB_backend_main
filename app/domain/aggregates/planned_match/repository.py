from abc import ABC, abstractmethod
from uuid import UUID

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch


class PlannedMatchRepository(ABC):
    @abstractmethod
    async def get_by_id_with_lock(
        self, league_id: LeagueId, planned_match_id: UUID
    ) -> PlannedMatch | None: ...

    @abstractmethod
    async def delete(self, league_id: LeagueId, planned_match_id: UUID) -> None:
        """Delete the scoped plan, raising PlannedMatchNotFoundError if absent."""
        ...

    @abstractmethod
    async def upsert_many(self, matches: list[PlannedMatch]) -> None: ...

    @abstractmethod
    async def get_all_by_league(self, league_id: LeagueId) -> list[PlannedMatch]:
        """Return plans ordered by ascending UUID."""
        ...
