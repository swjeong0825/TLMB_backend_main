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
    async def get_all_by_team(self, team_id: TeamId, league_id: LeagueId) -> list[Match]: ...

    @abstractmethod
    async def get_all_by_player(
        self, league_id: LeagueId, team_ids: list[TeamId]
    ) -> list[Match]:
        """Return matches for any of the supplied team IDs in `league_id`.

        Used by `GetMatchHistoryByPlayerUseCase` under v3 OTPP=false, where a
        player may belong to multiple teams. The caller is responsible for
        resolving the player's team IDs from the League aggregate.

        Returns an empty list when `team_ids` is empty. Sorted by `created_at`
        descending. A single match cannot match more than one row even if both
        team IDs in the match are in the supplied list (one DB row per match).
        """
        ...

    @abstractmethod
    async def has_matches_for_team(self, team_id: TeamId, league_id: LeagueId) -> bool: ...

    @abstractmethod
    async def exists_match_for_team_pair(
        self, league_id: LeagueId, team1_id: TeamId, team2_id: TeamId
    ) -> bool: ...

    @abstractmethod
    async def save(self, match: Match) -> None: ...

    @abstractmethod
    async def delete(self, match_id: MatchId, league_id: LeagueId) -> None: ...
