from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.aggregates.planned_match.repository import PlannedMatchRepository
from app.infrastructure.persistence.models.orm_models import PlannedMatchORM


class SqlAlchemyPlannedMatchRepository(PlannedMatchRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
