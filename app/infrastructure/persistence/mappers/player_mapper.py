from __future__ import annotations

import uuid

from app.domain.aggregates.league.entities import Player
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PlayerNickname
from app.infrastructure.persistence.models.orm_models import PlayerORM


def player_to_domain(orm: PlayerORM) -> Player:
    return Player(
        player_id=PlayerId(value=orm.player_id),
        nickname=PlayerNickname(orm.nickname_normalized),
    )


def player_to_orm(domain: Player, league_id: LeagueId) -> PlayerORM:
    return PlayerORM(
        player_id=domain.player_id.value,
        league_id=league_id.value,
        nickname_normalized=domain.nickname.value,
    )
