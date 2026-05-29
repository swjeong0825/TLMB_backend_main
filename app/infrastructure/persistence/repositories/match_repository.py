from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.match.value_objects import MatchId
from app.infrastructure.persistence.mappers.match_mapper import match_to_domain, match_to_orm
from app.infrastructure.persistence.models.orm_models import MatchORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyMatchRepository(MatchRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, match_id: MatchId, league_id: LeagueId) -> Match | None:
        result = await self._session.execute(
            select(MatchORM).where(
                MatchORM.match_id == match_id.value,
                MatchORM.league_id == league_id.value,
            )
        )
        orm = result.scalar_one_or_none()
        return match_to_domain(orm) if orm is not None else None

    async def get_all_by_league(
        self,
        league_id: LeagueId,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Match]:
        filters = [MatchORM.league_id == league_id.value]
        if start_at is not None:
            filters.append(MatchORM.created_at >= start_at)
        if end_at is not None:
            filters.append(MatchORM.created_at < end_at)
        result = await self._session.execute(
            select(MatchORM)
            .where(*filters)
            .order_by(MatchORM.created_at.desc())
        )
        return [match_to_domain(row) for row in result.scalars().all()]

    async def get_latest_by_league(self, league_id: LeagueId) -> Match | None:
        result = await self._session.execute(
            select(MatchORM)
            .where(MatchORM.league_id == league_id.value)
            .order_by(MatchORM.created_at.desc())
            .limit(1)
        )
        orm = result.scalar_one_or_none()
        return match_to_domain(orm) if orm is not None else None

    async def get_all_by_pair(self, pair_id: PairId, league_id: LeagueId) -> list[Match]:
        result = await self._session.execute(
            select(MatchORM)
            .where(
                MatchORM.league_id == league_id.value,
                (MatchORM.pair1_id == pair_id.value) | (MatchORM.pair2_id == pair_id.value),
            )
            .order_by(MatchORM.created_at.desc())
        )
        return [match_to_domain(row) for row in result.scalars().all()]

    async def get_all_by_player(
        self, league_id: LeagueId, pair_ids: list[PairId]
    ) -> list[Match]:
        if not pair_ids:
            return []
        tids = [t.value for t in pair_ids]
        result = await self._session.execute(
            select(MatchORM)
            .where(
                MatchORM.league_id == league_id.value,
                or_(MatchORM.pair1_id.in_(tids), MatchORM.pair2_id.in_(tids)),
            )
            .order_by(MatchORM.created_at.desc())
        )
        return [match_to_domain(row) for row in result.scalars().all()]

    async def has_matches_for_pair(self, pair_id: PairId, league_id: LeagueId) -> bool:
        result = await self._session.execute(
            select(MatchORM).where(
                MatchORM.league_id == league_id.value,
                (MatchORM.pair1_id == pair_id.value) | (MatchORM.pair2_id == pair_id.value),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def exists_match_for_pair_matchup(
        self, league_id: LeagueId, pair1_id: PairId, pair2_id: PairId
    ) -> bool:
        pair1_uuid, pair2_uuid = pair1_id.value, pair2_id.value
        result = await self._session.execute(
            select(MatchORM.match_id)
            .where(
                MatchORM.league_id == league_id.value,
                or_(
                    and_(
                        MatchORM.pair1_id == pair1_uuid,
                        MatchORM.pair2_id == pair2_uuid,
                    ),
                    and_(
                        MatchORM.pair1_id == pair2_uuid,
                        MatchORM.pair2_id == pair1_uuid,
                    ),
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def exists_match_for_pair_matchup_between(
        self,
        league_id: LeagueId,
        pair1_id: PairId,
        pair2_id: PairId,
        start_at: datetime,
        end_at: datetime,
    ) -> bool:
        pair1_uuid, pair2_uuid = pair1_id.value, pair2_id.value
        result = await self._session.execute(
            select(MatchORM.match_id)
            .where(
                MatchORM.league_id == league_id.value,
                MatchORM.created_at >= start_at,
                MatchORM.created_at < end_at,
                or_(
                    and_(
                        MatchORM.pair1_id == pair1_uuid,
                        MatchORM.pair2_id == pair2_uuid,
                    ),
                    and_(
                        MatchORM.pair1_id == pair2_uuid,
                        MatchORM.pair2_id == pair1_uuid,
                    ),
                ),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def save(self, match: Match) -> None:
        match_orm = await self._session.get(MatchORM, match.match_id.value)
        if match_orm is None:
            match_orm = match_to_orm(match)
            self._session.add(match_orm)
            # Flush so the DB `server_default=now()` populates `created_at`
            # and we can hand the authoritative server timestamp back to
            # the caller (the SubmitMatchResultResponse needs it for the
            # frontend's player-edit-window math).
            await self._session.flush()
            match.created_at = match_orm.created_at
        else:
            match_orm.pair1_score = match.set_score.pair1_score
            match_orm.pair2_score = match.set_score.pair2_score
            match_orm.updated_at = _utcnow()

    async def delete(self, match_id: MatchId, league_id: LeagueId) -> None:
        result = await self._session.execute(
            select(MatchORM).where(
                MatchORM.match_id == match_id.value,
                MatchORM.league_id == league_id.value,
            )
        )
        match_orm = result.scalar_one_or_none()
        if match_orm is not None:
            await self._session.delete(match_orm)
