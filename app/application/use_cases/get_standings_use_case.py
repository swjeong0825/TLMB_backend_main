from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator, StandingsEntry


@dataclass
class GetStandingsQuery:
    league_id: str


class GetStandingsUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._calculator = StandingsCalculator()

    async def execute(self, query: GetStandingsQuery) -> list[StandingsEntry]:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        matches = await self._match_repo.get_all_by_league(league_id)

        return self._calculator.compute(matches, league.teams, league.players)
