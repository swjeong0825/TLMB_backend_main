from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId


class SinglesMatchRepository(ABC):
    @abstractmethod
    async def get_by_id(
        self, match_id: SinglesMatchId, league_id: LeagueId
    ) -> SinglesMatch | None: ...

    @abstractmethod
    async def get_all_by_league(
        self,
        league_id: LeagueId,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[SinglesMatch]: ...

    @abstractmethod
    async def get_latest_by_league(
        self, league_id: LeagueId
    ) -> SinglesMatch | None: ...

    @abstractmethod
    async def get_all_by_player(
        self, league_id: LeagueId, player_id: PlayerId
    ) -> list[SinglesMatch]: ...

    @abstractmethod
    async def save(self, match: SinglesMatch) -> None: ...

    @abstractmethod
    async def delete(self, match_id: SinglesMatchId, league_id: LeagueId) -> None: ...
