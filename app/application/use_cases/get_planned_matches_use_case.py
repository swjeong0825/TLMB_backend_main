from dataclasses import dataclass

from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.repository import PlannedMatchRepository
from app.domain.exceptions import LeagueNotFoundError


@dataclass(frozen=True)
class GetPlannedMatchesQuery:
    league_id: str


class GetPlannedMatchesUseCase:
    def __init__(self, league_repo: LeagueRepository, planned_match_repo: PlannedMatchRepository) -> None:
        self._league_repo = league_repo
        self._planned_match_repo = planned_match_repo

    async def execute(self, query: GetPlannedMatchesQuery) -> list[PlannedMatchRecord]:
        league_id = LeagueId.from_str(query.league_id)
        if not await self._league_repo.exists(league_id):
            raise LeagueNotFoundError(f"League '{league_id}' not found")
        matches = await self._planned_match_repo.get_all_by_league(league_id)
        return [PlannedMatchRecord(match.id, match.value.value) for match in matches]
