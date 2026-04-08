from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.infrastructure.persistence.mappers.league_mapper import league_to_domain
from app.infrastructure.persistence.mappers.player_mapper import player_to_orm
from app.infrastructure.persistence.mappers.team_mapper import team_to_orm
from app.infrastructure.persistence.models.orm_models import LeagueORM, PlayerORM, TeamORM


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SqlAlchemyLeagueRepository(LeagueRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, league_id: LeagueId) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(selectinload(LeagueORM.players), selectinload(LeagueORM.teams))
            .where(LeagueORM.league_id == league_id.value)
        )
        orm = result.scalar_one_or_none()
        return league_to_domain(orm) if orm is not None else None

    async def get_by_id_with_lock(self, league_id: LeagueId) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(selectinload(LeagueORM.players), selectinload(LeagueORM.teams))
            .where(LeagueORM.league_id == league_id.value)
            .with_for_update()
        )
        orm = result.scalar_one_or_none()
        return league_to_domain(orm) if orm is not None else None

    async def get_by_normalized_title(self, normalized_title: str) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(selectinload(LeagueORM.players), selectinload(LeagueORM.teams))
            .where(LeagueORM.title_normalized == normalized_title)
        )
        orm = result.scalar_one_or_none()
        return league_to_domain(orm) if orm is not None else None

    async def save(self, league: League) -> None:
        league_orm = await self._session.get(LeagueORM, league.league_id.value)
        if league_orm is None:
            league_orm = LeagueORM(
                league_id=league.league_id.value,
                title=league.title,
                title_normalized=league.title.lower().strip(),
                host_token=league.host_token.value,
                description=league.description,
                rules=league.rules.to_dict(),
            )
            self._session.add(league_orm)
        else:
            league_orm.title = league.title
            league_orm.title_normalized = league.title.lower().strip()
            league_orm.description = league.description
            league_orm.rules = league.rules.to_dict()
            league_orm.updated_at = _utcnow()

        for player in league.players:
            player_orm = await self._session.get(PlayerORM, player.player_id.value)
            if player_orm is None:
                player_orm = player_to_orm(player, league.league_id)
                self._session.add(player_orm)
            else:
                player_orm.nickname_normalized = player.nickname.value
                player_orm.updated_at = _utcnow()

        existing_team_ids = {t.team_id.value for t in league.teams}
        for team in league.teams:
            team_orm = await self._session.get(TeamORM, team.team_id.value)
            if team_orm is None:
                team_orm = team_to_orm(team, league.league_id)
                self._session.add(team_orm)

        for team_id in league.pending_deleted_team_ids:
            team_orm = await self._session.get(TeamORM, team_id.value)
            if team_orm is not None:
                await self._session.delete(team_orm)
