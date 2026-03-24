from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId


class MatchRepository(ABC):
    @abstractmethod
    async def get_by_id(self, match_id: MatchId, league_id: LeagueId) -> Match | None: ...

    @abstractmethod
    async def get_all_by_league(self, league_id: LeagueId) -> list[Match]: ...

    @abstractmethod
    async def has_matches_for_team(self, team_id: TeamId, league_id: LeagueId) -> bool: ...

    @abstractmethod
    async def save(self, match: Match) -> None: ...

    @abstractmethod
    async def delete(self, match_id: MatchId, league_id: LeagueId) -> None: ...
