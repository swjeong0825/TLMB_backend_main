from __future__ import annotations

from app.domain.aggregates.league.entities import EligiblePlayer
from app.domain.aggregates.league.value_objects import (
    EligiblePlayerId,
    LeagueId,
    PlayerNickname,
)
from app.infrastructure.persistence.models.orm_models import EligiblePlayerORM


def eligible_player_to_domain(orm: EligiblePlayerORM) -> EligiblePlayer:
    return EligiblePlayer(
        eligible_player_id=EligiblePlayerId(value=orm.eligible_player_id),
        nickname=PlayerNickname(orm.nickname_normalized),
    )


def eligible_player_to_orm(
    domain: EligiblePlayer, league_id: LeagueId
) -> EligiblePlayerORM:
    return EligiblePlayerORM(
        eligible_player_id=domain.eligible_player_id.value,
        league_id=league_id.value,
        nickname_normalized=domain.nickname.value,
    )
