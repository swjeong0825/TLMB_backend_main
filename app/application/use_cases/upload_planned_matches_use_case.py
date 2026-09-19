from collections.abc import Callable
from dataclasses import dataclass

from app.application.unit_of_work.upload_planned_matches_uow import UploadPlannedMatchesUnitOfWork
from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.exceptions import InvalidPlannedMatchError, LeagueNotFoundError


@dataclass(frozen=True)
class UploadPlannedMatchesCommand:
    league_id: str
    matches: list[PlannedMatchRecord]


class UploadPlannedMatchesUseCase:
    def __init__(self, uow_factory: Callable[[], UploadPlannedMatchesUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: UploadPlannedMatchesCommand) -> list[PlannedMatchRecord]:
        if not command.matches:
            raise InvalidPlannedMatchError("matches must be a non-empty list")
        if len({match.id for match in command.matches}) != len(command.matches):
            raise InvalidPlannedMatchError("Duplicate planned match IDs in the same request")
        league_id = LeagueId.from_str(command.league_id)
        matches = [
            PlannedMatch.create(league_id, record.id, record.value)
            for record in command.matches
        ]
        async with self._uow_factory() as uow:
            if not await uow.league_repo.exists(league_id):
                raise LeagueNotFoundError(f"League '{league_id}' not found")
            await uow.planned_match_repo.upsert_many(matches)
            await uow.commit()
        return [PlannedMatchRecord(match.id, match.value.value) for match in matches]
