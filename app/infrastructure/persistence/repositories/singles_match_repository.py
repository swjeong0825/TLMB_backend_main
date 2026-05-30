from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId
from app.infrastructure.persistence.mappers.singles_match_mapper import (
    singles_match_to_domain,
    singles_match_to_orm,
)
from app.infrastructure.persistence.models.orm_models import SinglesMatchORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemySinglesMatchRepository(SinglesMatchRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(
        self, match_id: SinglesMatchId, league_id: LeagueId
    ) -> SinglesMatch | None:
        result = await self._session.execute(
            select(SinglesMatchORM).where(
                SinglesMatchORM.match_id == match_id.value,
                SinglesMatchORM.league_id == league_id.value,
            )
        )
        orm = result.scalar_one_or_none()
        return singles_match_to_domain(orm) if orm is not None else None

    async def get_all_by_league(
        self,
        league_id: LeagueId,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[SinglesMatch]:
        filters = [SinglesMatchORM.league_id == league_id.value]
        if start_at is not None:
            filters.append(SinglesMatchORM.created_at >= start_at)
        if end_at is not None:
            filters.append(SinglesMatchORM.created_at < end_at)
        result = await self._session.execute(
            select(SinglesMatchORM)
            .where(*filters)
            .order_by(SinglesMatchORM.created_at.desc())
        )
        return [singles_match_to_domain(row) for row in result.scalars().all()]

    async def get_latest_by_league(
        self, league_id: LeagueId
    ) -> SinglesMatch | None:
        result = await self._session.execute(
            select(SinglesMatchORM)
            .where(SinglesMatchORM.league_id == league_id.value)
            .order_by(SinglesMatchORM.created_at.desc())
            .limit(1)
        )
        orm = result.scalar_one_or_none()
        return singles_match_to_domain(orm) if orm is not None else None

    async def get_all_by_player(
        self, league_id: LeagueId, player_id: PlayerId
    ) -> list[SinglesMatch]:
        result = await self._session.execute(
            select(SinglesMatchORM)
            .where(
                SinglesMatchORM.league_id == league_id.value,
                or_(
                    SinglesMatchORM.player1_id == player_id.value,
                    SinglesMatchORM.player2_id == player_id.value,
                ),
            )
            .order_by(SinglesMatchORM.created_at.desc())
        )
        return [singles_match_to_domain(row) for row in result.scalars().all()]

    async def save(self, match: SinglesMatch) -> None:
        match_orm = await self._session.get(SinglesMatchORM, match.match_id.value)
        if match_orm is None:
            match_orm = singles_match_to_orm(match)
            self._session.add(match_orm)
            await self._session.flush()
            match.created_at = match_orm.created_at
        else:
            match_orm.player1_score = match.set_score.pair1_score
            match_orm.player2_score = match.set_score.pair2_score
            match_orm.updated_at = _utcnow()

    async def delete(self, match_id: SinglesMatchId, league_id: LeagueId) -> None:
        result = await self._session.execute(
            select(SinglesMatchORM).where(
                SinglesMatchORM.match_id == match_id.value,
                SinglesMatchORM.league_id == league_id.value,
            )
        )
        match_orm = result.scalar_one_or_none()
        if match_orm is not None:
            await self._session.delete(match_orm)
