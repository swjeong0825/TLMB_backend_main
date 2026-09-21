from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.application.unit_of_work.delete_planned_match_uow import DeletePlannedMatchUnitOfWork
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError


@dataclass(frozen=True)
class DeletePlannedMatchCommand:
    league_id: str
    planned_match_id: UUID


class DeletePlannedMatchUseCase:
    def __init__(self, uow_factory: Callable[[], DeletePlannedMatchUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: DeletePlannedMatchCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)
        async with self._uow_factory() as uow:
            # Match the league-before-plan lock order used by uploads and recording.
            if not await uow.league_repo.lock_by_id(league_id):
                raise LeagueNotFoundError(f"League '{league_id}' not found")
            await uow.planned_match_repo.delete(league_id, command.planned_match_id)
            await uow.commit()
