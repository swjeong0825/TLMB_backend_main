from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app.application.use_cases.get_standings_use_case import (
    StandingsScope,
    StandingsView,
    league_date_filter_to_utc_bounds,
)
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator


@dataclass
class GetStandingsByPlayerQuery:
    league_id: str
    player_name: str
    start_date: date | None = None
    end_date: date | None = None
    scope: StandingsScope = "doubles"


class GetStandingsByPlayerUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
        singles_match_repo: SinglesMatchRepository | None = None,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._singles_match_repo = singles_match_repo
        self._calculator = StandingsCalculator()

    async def execute(self, query: GetStandingsByPlayerQuery) -> StandingsView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        normalized_name = PlayerNickname(query.player_name)
        player = next(
            (p for p in league.players if p.has_nickname(normalized_name)),
            None,
        )
        if player is None:
            raise PlayerNotFoundError(
                f"Player '{query.player_name}' not found in league '{query.league_id}'"
            )

        start_at, end_at = league_date_filter_to_utc_bounds(
            query.start_date,
            query.end_date,
            league.league_timezone.value,
        )
        matches = []
        singles_matches = []
        if query.scope in ("doubles", "both"):
            matches = await self._get_doubles_matches(league_id, start_at, end_at)
        if query.scope in ("singles", "both"):
            singles_matches = await self._get_singles_matches(league_id, start_at, end_at)

        if query.scope == "singles":
            all_entries = self._calculator.compute_singles(
                singles_matches,
                league.players,
                league.rules,
            )
        elif query.scope == "both":
            all_entries = self._calculator.compute_combined(
                matches,
                league.pairs,
                singles_matches,
                league.players,
                league.rules,
            )
        else:
            all_entries = self._calculator.compute(
                matches, league.pairs, league.players, league.rules
            )

        if query.scope in ("singles", "both") or league.rules.ranking_subject == "player":
            pid = str(player.player_id.value)
            filtered = [e for e in all_entries if e.player_id == pid]
            return StandingsView(entries=filtered, tie_breakers=league.rules.tie_breakers)

        # Subject = "pair": surface every pair the player belongs to.
        # Under OTPP=true the player has at most one pair, so the result is a
        # single-element array (or empty if all of their pairs have been
        # deleted). Under OTPP=false a player may belong to multiple pairs and
        # all of their pair rows are returned. See design doc 18.
        player_pair_ids = {
            str(t.pair_id.value)
            for t in league.pairs
            if t.player_id_1 == player.player_id or t.player_id_2 == player.player_id
        }
        if not player_pair_ids:
            return StandingsView(entries=[], tie_breakers=league.rules.tie_breakers)

        filtered = [e for e in all_entries if e.pair_id in player_pair_ids]
        return StandingsView(entries=filtered, tie_breakers=league.rules.tie_breakers)

    async def _get_doubles_matches(
        self,
        league_id: LeagueId,
        start_at,
        end_at,
    ):
        if start_at is None and end_at is None:
            return await self._match_repo.get_all_by_league(league_id)
        return await self._match_repo.get_all_by_league(
            league_id, start_at=start_at, end_at=end_at
        )

    async def _get_singles_matches(
        self,
        league_id: LeagueId,
        start_at,
        end_at,
    ):
        if self._singles_match_repo is None:
            return []
        if start_at is None and end_at is None:
            return await self._singles_match_repo.get_all_by_league(league_id)
        return await self._singles_match_repo.get_all_by_league(
            league_id, start_at=start_at, end_at=end_at
        )
