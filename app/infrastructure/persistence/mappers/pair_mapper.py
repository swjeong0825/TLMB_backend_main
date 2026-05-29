from __future__ import annotations

from app.domain.aggregates.league.entities import Pair
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PairId
from app.infrastructure.persistence.models.orm_models import PairORM


def pair_to_domain(orm: PairORM) -> Pair:
    return Pair(
        pair_id=PairId(value=orm.pair_id),
        player_id_1=PlayerId(value=orm.player_id_1),
        player_id_2=PlayerId(value=orm.player_id_2),
    )


def pair_to_orm(domain: Pair, league_id: LeagueId) -> PairORM:
    return PairORM(
        pair_id=domain.pair_id.value,
        league_id=league_id.value,
        player_id_1=domain.player_id_1.value,
        player_id_2=domain.player_id_2.value,
    )
