from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.league_rules import RankingMetric
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator, StandingsEntry


@dataclass
class GetStandingsQuery:
    league_id: str


@dataclass(frozen=True)
class StandingsView:
    """Use case result bundling computed standings with the league's ranking config.

    `tie_breakers` is the league's ordered ranking metric tuple (see
    `Design_Doc/TLMB_Design_doc/17_configurable_ranking.md`). The router exposes
    it on the standings response so clients can label the displayed metric
    column to match what the league is actually ranked by — e.g. a league
    configured with `tie_breakers=["games_won", ...]` shows a "Games won"
    column rather than the previously hard-coded "Games ±".
    """

    entries: list[StandingsEntry]
    tie_breakers: tuple[RankingMetric, ...]


class GetStandingsUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._calculator = StandingsCalculator()

    async def execute(self, query: GetStandingsQuery) -> StandingsView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        matches = await self._match_repo.get_all_by_league(league_id)

        entries = self._calculator.compute(
            matches, league.teams, league.players, league.rules
        )
        return StandingsView(entries=entries, tie_breakers=league.rules.tie_breakers)
