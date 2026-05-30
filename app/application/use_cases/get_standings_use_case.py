from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from app.domain.aggregates.league.league_rules import RankingMetric, RankingSubject
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository
from app.domain.exceptions import LeagueNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator, StandingsEntry

StandingsScope = Literal["doubles", "singles", "both"]


@dataclass
class GetStandingsQuery:
    league_id: str
    start_date: date | None = None
    end_date: date | None = None
    subject: RankingSubject | None = None
    scope: StandingsScope = "doubles"


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
        singles_match_repo: SinglesMatchRepository | None = None,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._singles_match_repo = singles_match_repo
        self._calculator = StandingsCalculator()

    async def execute(self, query: GetStandingsQuery) -> StandingsView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

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
            entries = self._calculator.compute_singles(
                singles_matches,
                league.players,
                league.rules,
            )
        elif query.scope == "both":
            entries = self._calculator.compute_combined(
                matches,
                league.pairs,
                singles_matches,
                league.players,
                league.rules,
            )
        else:
            entries = self._calculator.compute(
                matches,
                league.pairs,
                league.players,
                league.rules,
                subject=query.subject,
            )
        return StandingsView(entries=entries, tie_breakers=league.rules.tie_breakers)

    async def _get_doubles_matches(
        self,
        league_id: LeagueId,
        start_at: datetime | None,
        end_at: datetime | None,
    ):
        if start_at is None and end_at is None:
            return await self._match_repo.get_all_by_league(league_id)
        return await self._match_repo.get_all_by_league(
            league_id, start_at=start_at, end_at=end_at
        )

    async def _get_singles_matches(
        self,
        league_id: LeagueId,
        start_at: datetime | None,
        end_at: datetime | None,
    ):
        if self._singles_match_repo is None:
            return []
        if start_at is None and end_at is None:
            return await self._singles_match_repo.get_all_by_league(league_id)
        return await self._singles_match_repo.get_all_by_league(
            league_id, start_at=start_at, end_at=end_at
        )


def league_date_filter_to_utc_bounds(
    start_date: date | None,
    end_date: date | None,
    league_timezone: str,
) -> tuple[datetime | None, datetime | None]:
    """Convert inclusive league-local date filters into UTC datetimes."""
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")

    tz = ZoneInfo(league_timezone)
    start_at = (
        datetime.combine(start_date, time.min, tzinfo=tz).astimezone(timezone.utc)
        if start_date is not None
        else None
    )
    end_at = (
        datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz).astimezone(
            timezone.utc
        )
        if end_date is not None
        else None
    )
    return start_at, end_at
