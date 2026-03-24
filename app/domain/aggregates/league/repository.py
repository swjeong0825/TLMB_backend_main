from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.value_objects import LeagueId


class LeagueRepository(ABC):
    @abstractmethod
    async def get_by_id(self, league_id: LeagueId) -> League | None: ...

    @abstractmethod
    async def get_by_id_with_lock(self, league_id: LeagueId) -> League | None: ...

    @abstractmethod
    async def get_by_normalized_title(self, normalized_title: str) -> League | None: ...

    @abstractmethod
    async def save(self, league: League) -> None: ...
