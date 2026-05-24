from __future__ import annotations

import uuid
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
from app.infrastructure.persistence.models.orm_models import (
    LeagueORM,
    MatchORM,
    PlayerORM,
    TeamORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _escape_sql_like_prefix(prefix: str) -> str:
    """Escape %, _, and \\ so the prefix is matched literally in SQL LIKE."""
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyLeagueRepository(LeagueRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    _LEAGUE_LOAD_OPTIONS = (
        selectinload(LeagueORM.players),
        selectinload(LeagueORM.teams),
    )

    async def get_by_id(self, league_id: LeagueId) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(*self._LEAGUE_LOAD_OPTIONS)
            .where(LeagueORM.league_id == league_id.value)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        counts = await self._load_match_counts_by_player(league_id, orm)
        return league_to_domain(orm, counts)

    async def get_by_id_with_lock(self, league_id: LeagueId) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(*self._LEAGUE_LOAD_OPTIONS)
            .where(LeagueORM.league_id == league_id.value)
            .with_for_update()
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        counts = await self._load_match_counts_by_player(league_id, orm)
        return league_to_domain(orm, counts)

    async def get_by_normalized_title(self, normalized_title: str) -> League | None:
        result = await self._session.execute(
            select(LeagueORM)
            .options(*self._LEAGUE_LOAD_OPTIONS)
            .where(LeagueORM.title_normalized == normalized_title)
        )
        orm = result.scalar_one_or_none()
        if orm is None:
            return None
        counts = await self._load_match_counts_by_player(
            LeagueId(value=orm.league_id), orm
        )
        return league_to_domain(orm, counts)

    async def search_by_title_prefix(self, normalized_prefix: str, limit: int) -> list[tuple[str, str]]:
        pattern = _escape_sql_like_prefix(normalized_prefix) + "%"
        result = await self._session.execute(
            select(LeagueORM.league_id, LeagueORM.title)
            .where(LeagueORM.title_normalized.like(pattern, escape="\\"))
            .order_by(LeagueORM.title_normalized.asc())
            .limit(limit)
        )
        return [(str(row.league_id), row.title) for row in result.all()]

    async def save(self, league: League) -> None:
        league_orm = await self._session.get(LeagueORM, league.league_id.value)
        if league_orm is None:
            league_orm = LeagueORM(
                league_id=league.league_id.value,
                title=league.title,
                title_normalized=league.title.lower().strip(),
                host_token=league.host_token.value,
                host_email=league.host_email.value,
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

        for player_id in league.pending_deleted_player_ids:
            player_orm = await self._session.get(PlayerORM, player_id.value)
            if player_orm is not None:
                await self._session.delete(player_orm)

        for team in league.teams:
            team_orm = await self._session.get(TeamORM, team.team_id.value)
            if team_orm is None:
                team_orm = team_to_orm(team, league.league_id)
                self._session.add(team_orm)

        for team_id in league.pending_deleted_team_ids:
            team_orm = await self._session.get(TeamORM, team_id.value)
            if team_orm is not None:
                await self._session.delete(team_orm)

    async def _load_match_counts_by_player(
        self,
        league_id: LeagueId,
        league_orm: LeagueORM,
    ) -> dict[uuid.UUID, int]:
        """Compute per-player match-participation counts for `remove_player`.

        Issues a single small query for all matches in the league (matches
        are typically small in this domain) and aggregates counts per player
        in Python by walking the loaded `teams`. Returns `{player_id: count}`;
        players with zero matches are simply absent from the dict so
        callers should `.get(pid, 0)`.

        Note: a match always references two distinct teams whose player
        rosters are disjoint (enforced by `SamePlayerOnBothTeamsError`), so
        summing per-team match counts across a player's teams is correct —
        no double-counting is possible.
        """
        if not league_orm.teams:
            return {}

        result = await self._session.execute(
            select(MatchORM.team1_id, MatchORM.team2_id)
            .where(MatchORM.league_id == league_id.value)
        )
        match_count_by_team: dict[uuid.UUID, int] = {}
        for row in result:
            t1 = row.team1_id
            t2 = row.team2_id
            match_count_by_team[t1] = match_count_by_team.get(t1, 0) + 1
            match_count_by_team[t2] = match_count_by_team.get(t2, 0) + 1

        counts_by_player: dict[uuid.UUID, int] = {}
        for team in league_orm.teams:
            cnt = match_count_by_team.get(team.team_id, 0)
            if cnt:
                counts_by_player[team.player_id_1] = (
                    counts_by_player.get(team.player_id_1, 0) + cnt
                )
                counts_by_player[team.player_id_2] = (
                    counts_by_player.get(team.player_id_2, 0) + cnt
                )
        return counts_by_player
