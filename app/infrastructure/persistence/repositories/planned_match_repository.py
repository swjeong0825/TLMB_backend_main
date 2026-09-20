from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.aggregates.planned_match.repository import PlannedMatchRepository
from app.domain.exceptions import PlannedMatchNotFoundError
from app.infrastructure.persistence.models.orm_models import PlannedMatchORM


class SqlAlchemyPlannedMatchRepository(PlannedMatchRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id_with_lock(
        self, league_id: LeagueId, planned_match_id: UUID
    ) -> PlannedMatch | None:
        row = (await self._session.execute(
            select(PlannedMatchORM.id, PlannedMatchORM.value)
            .where(
                PlannedMatchORM.league_id == league_id.value,
                PlannedMatchORM.id == planned_match_id,
            )
            .with_for_update()
        )).one_or_none()
        return PlannedMatch.create(league_id, row.id, row.value) if row is not None else None

    async def delete(self, league_id: LeagueId, planned_match_id: UUID) -> None:
        deleted_id = await self._session.scalar(
            delete(PlannedMatchORM)
            .where(
                PlannedMatchORM.league_id == league_id.value,
                PlannedMatchORM.id == planned_match_id,
            )
            .returning(PlannedMatchORM.id)
        )
        if deleted_id is None:
            raise PlannedMatchNotFoundError(
                f"Planned match '{planned_match_id}' not found in this league"
            )

    async def upsert_many(self, matches: list[PlannedMatch]) -> None:
        if not matches:
            return
        statement = insert(PlannedMatchORM)
        statement = statement.on_conflict_do_update(
            index_elements=[PlannedMatchORM.league_id, PlannedMatchORM.id],
            set_={"value": statement.excluded.value},
        )
        # Consistent lock order for overlapping batches; the caller retains response order.
        await self._session.execute(statement, [
            {"league_id": match.league_id.value, "id": match.id, "value": match.value.value}
            for match in sorted(matches, key=lambda match: (match.league_id.value, match.id))
        ])

    async def get_all_by_league(self, league_id: LeagueId) -> list[PlannedMatch]:
        rows = (await self._session.execute(
            select(PlannedMatchORM.id, PlannedMatchORM.value)
            .where(PlannedMatchORM.league_id == league_id.value)
            .order_by(PlannedMatchORM.id.asc())
        )).all()
        return [PlannedMatch.create(league_id, row.id, row.value) for row in rows]
