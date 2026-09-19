from __future__ import annotations

import uuid

from app.domain.aggregates.league.entities import Player
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PlayerNickname
from app.infrastructure.persistence.models.orm_models import PlayerAliasORM, PlayerORM


def player_to_domain(orm: PlayerORM) -> Player:
    return Player(
        player_id=PlayerId(value=orm.player_id),
        nicknames=[
            PlayerNickname.from_persisted(alias.alias_normalized)
            for alias in orm.aliases
        ],
        rating=orm.rating,
    )


def player_to_orm(domain: Player, league_id: LeagueId) -> PlayerORM:
    return PlayerORM(
        player_id=domain.player_id.value,
        league_id=league_id.value,
        rating=domain.rating,
        aliases=[
            PlayerAliasORM(
                player_id=domain.player_id.value,
                league_id=league_id.value,
                alias_normalized=nickname.value,
                is_canonical=index == 0,
            )
            for index, nickname in enumerate(domain.nicknames)
        ],
    )
