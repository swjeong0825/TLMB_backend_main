from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.aggregates.league.value_objects import LeagueId, TeamId
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

    async def get_all_by_league(self, league_id: LeagueId) -> list[Match]:
        result = await self._session.execute(
            select(MatchORM)
            .where(MatchORM.league_id == league_id.value)
            .order_by(MatchORM.created_at.desc())
        )
        return [match_to_domain(row) for row in result.scalars().all()]

    async def get_all_by_team(self, team_id: TeamId, league_id: LeagueId) -> list[Match]:
        result = await self._session.execute(
            select(MatchORM)
            .where(
                MatchORM.league_id == league_id.value,
                (MatchORM.team1_id == team_id.value) | (MatchORM.team2_id == team_id.value),
            )
            .order_by(MatchORM.created_at.desc())
        )
        return [match_to_domain(row) for row in result.scalars().all()]

    async def has_matches_for_team(self, team_id: TeamId, league_id: LeagueId) -> bool:
        result = await self._session.execute(
            select(MatchORM).where(
                MatchORM.league_id == league_id.value,
                (MatchORM.team1_id == team_id.value) | (MatchORM.team2_id == team_id.value),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def exists_match_for_team_pair(
        self, league_id: LeagueId, team1_id: TeamId, team2_id: TeamId
    ) -> bool:
        t1, t2 = team1_id.value, team2_id.value
        result = await self._session.execute(
            select(MatchORM.match_id)
            .where(
                MatchORM.league_id == league_id.value,
                or_(
                    and_(MatchORM.team1_id == t1, MatchORM.team2_id == t2),
                    and_(MatchORM.team1_id == t2, MatchORM.team2_id == t1),
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
        else:
            match_orm.team1_score = match.set_score.team1_score
            match_orm.team2_score = match.set_score.team2_score
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
