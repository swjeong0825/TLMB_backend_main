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
from app.infrastructure.persistence.mappers.pair_mapper import pair_to_orm
from app.infrastructure.persistence.models.orm_models import (
    LeagueORM,
    MatchORM,
    PlayerAliasORM,
    PlayerORM,
    PairORM,
    SinglesMatchORM,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _escape_sql_like_prefix(prefix: str) -> str:
    """Escape %, _, and \\ so the prefix is matched literally in SQL LIKE."""
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class SqlAlchemyLeagueRepository(LeagueRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists(self, league_id: LeagueId) -> bool:
        return bool(await self._session.scalar(
            select(select(LeagueORM.league_id).where(
                LeagueORM.league_id == league_id.value
            ).exists())
        ))

    async def lock_by_id(self, league_id: LeagueId) -> bool:
        return await self._session.scalar(
            select(LeagueORM.league_id)
            .where(LeagueORM.league_id == league_id.value)
            .with_for_update()
        ) is not None

    _LEAGUE_LOAD_OPTIONS = (
        selectinload(LeagueORM.players).selectinload(PlayerORM.aliases),
        selectinload(LeagueORM.pairs),
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
                league_timezone=league.league_timezone.value,
                latest_match_date=league.latest_match_date,
                latest_match_date_single=league.latest_match_date_single,
                description=league.description,
                rules=league.rules.to_dict(),
            )
            self._session.add(league_orm)
        else:
            league_orm.title = league.title
            league_orm.title_normalized = league.title.lower().strip()
            league_orm.league_timezone = league.league_timezone.value
            league_orm.latest_match_date = league.latest_match_date
            league_orm.latest_match_date_single = league.latest_match_date_single
            league_orm.description = league.description
            league_orm.rules = league.rules.to_dict()
            league_orm.updated_at = _utcnow()

        for player in league.players:
            player_orm = await self._get_player_with_aliases(player.player_id.value)
            if player_orm is None:
                player_orm = player_to_orm(player, league.league_id)
                self._session.add(player_orm)
            else:
                player_orm.rating = player.rating
                player_orm.updated_at = _utcnow()
                await self._sync_player_aliases(player_orm, player, league.league_id)

        for player_id in league.pending_deleted_player_ids:
            player_orm = await self._session.get(PlayerORM, player_id.value)
            if player_orm is not None:
                await self._session.delete(player_orm)

        for pair in league.pairs:
            pair_orm = await self._session.get(PairORM, pair.pair_id.value)
            if pair_orm is None:
                pair_orm = pair_to_orm(pair, league.league_id)
                self._session.add(pair_orm)

        for pair_id in league.pending_deleted_pair_ids:
            pair_orm = await self._session.get(PairORM, pair_id.value)
            if pair_orm is not None:
                await self._session.delete(pair_orm)

    async def _get_player_with_aliases(self, player_id: uuid.UUID) -> PlayerORM | None:
        result = await self._session.execute(
            select(PlayerORM)
            .options(selectinload(PlayerORM.aliases))
            .where(PlayerORM.player_id == player_id)
        )
        return result.scalar_one_or_none()

    async def _sync_player_aliases(
        self,
        player_orm: PlayerORM,
        player,
        league_id: LeagueId,
    ) -> None:
        desired = [
            (nickname.value, index == 0)
            for index, nickname in enumerate(player.nicknames)
        ]
        desired_values = {alias for alias, _ in desired}
        desired_canonical = desired[0][0]

        # Clear the old canonical before promoting another existing alias.
        for alias_orm in player_orm.aliases:
            if (
                alias_orm.is_canonical
                and alias_orm.alias_normalized != desired_canonical
            ):
                alias_orm.is_canonical = False
        await self._session.flush()

        for alias_orm in list(player_orm.aliases):
            if alias_orm.alias_normalized not in desired_values:
                player_orm.aliases.remove(alias_orm)
        await self._session.flush()

        existing = {alias.alias_normalized: alias for alias in player_orm.aliases}
        for alias_normalized, is_canonical in desired:
            alias_orm = existing.get(alias_normalized)
            if alias_orm is None:
                player_orm.aliases.append(
                    PlayerAliasORM(
                        player_id=player.player_id.value,
                        league_id=league_id.value,
                        alias_normalized=alias_normalized,
                        is_canonical=is_canonical,
                    )
                )
            else:
                alias_orm.league_id = league_id.value
                alias_orm.is_canonical = is_canonical

    async def _load_match_counts_by_player(
        self,
        league_id: LeagueId,
        league_orm: LeagueORM,
    ) -> dict[uuid.UUID, int]:
        """Compute per-player match-participation counts for `remove_player`.

        Issues a single small query for all matches in the league (matches
        are typically small in this domain) and aggregates counts per player
        in Python by walking the loaded `pairs`. Returns `{player_id: count}`;
        players with zero matches are simply absent from the dict so
        callers should `.get(pid, 0)`.

        Note: a match always references two distinct pairs whose player
        rosters are disjoint (enforced by `SamePlayerOnBothPairsError`), so
        summing per-pair match counts across a player's pairs is correct —
        no double-counting is possible.
        """
        result = await self._session.execute(
            select(MatchORM.pair1_id, MatchORM.pair2_id).where(
                MatchORM.league_id == league_id.value
            )
        )
        match_count_by_pair: dict[uuid.UUID, int] = {}
        for row in result:
            pair1_id = row.pair1_id
            pair2_id = row.pair2_id
            match_count_by_pair[pair1_id] = match_count_by_pair.get(pair1_id, 0) + 1
            match_count_by_pair[pair2_id] = match_count_by_pair.get(pair2_id, 0) + 1

        counts_by_player: dict[uuid.UUID, int] = {}
        for pair in league_orm.pairs:
            cnt = match_count_by_pair.get(pair.pair_id, 0)
            if cnt:
                counts_by_player[pair.player_id_1] = (
                    counts_by_player.get(pair.player_id_1, 0) + cnt
                )
                counts_by_player[pair.player_id_2] = (
                    counts_by_player.get(pair.player_id_2, 0) + cnt
                )

        singles_result = await self._session.execute(
            select(SinglesMatchORM.player1_id, SinglesMatchORM.player2_id).where(
                SinglesMatchORM.league_id == league_id.value
            )
        )
        for row in singles_result:
            counts_by_player[row.player1_id] = (
                counts_by_player.get(row.player1_id, 0) + 1
            )
            counts_by_player[row.player2_id] = (
                counts_by_player.get(row.player2_id, 0) + 1
            )
        return counts_by_player
