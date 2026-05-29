from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId


class MatchRepository(ABC):
    @abstractmethod
    async def get_by_id(self, match_id: MatchId, league_id: LeagueId) -> Match | None: ...

    @abstractmethod
    async def get_all_by_league(
        self,
        league_id: LeagueId,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Match]:
        """Return league matches sorted newest first.

        Optional UTC bounds constrain `created_at` with an inclusive lower
        bound and exclusive upper bound.
        """
        ...

    @abstractmethod
    async def get_latest_by_league(self, league_id: LeagueId) -> Match | None: ...

    @abstractmethod
    async def get_all_by_pair(self, pair_id: PairId, league_id: LeagueId) -> list[Match]: ...

    @abstractmethod
    async def get_all_by_player(
        self, league_id: LeagueId, pair_ids: list[PairId]
    ) -> list[Match]:
        """Return matches for any of the supplied pair IDs in `league_id`.

        Used by `GetMatchHistoryByPlayerUseCase` under v3 OTPP=false, where a
        player may belong to multiple pairs. The caller is responsible for
        resolving the player's pair IDs from the League aggregate.

        Returns an empty list when `pair_ids` is empty. Sorted by `created_at`
        descending. A single match cannot match more than one row even if both
        pair IDs in the match are in the supplied list (one DB row per match).
        """
        ...

    @abstractmethod
    async def has_matches_for_pair(self, pair_id: PairId, league_id: LeagueId) -> bool: ...

    @abstractmethod
    async def exists_match_for_pair_matchup(
        self, league_id: LeagueId, pair1_id: PairId, pair2_id: PairId
    ) -> bool: ...

    @abstractmethod
    async def exists_match_for_pair_matchup_between(
        self,
        league_id: LeagueId,
        pair1_id: PairId,
        pair2_id: PairId,
        start_at: datetime,
        end_at: datetime,
    ) -> bool: ...

    @abstractmethod
    async def save(self, match: Match) -> None: ...

    @abstractmethod
    async def delete(self, match_id: MatchId, league_id: LeagueId) -> None: ...
