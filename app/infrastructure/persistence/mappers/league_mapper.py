from __future__ import annotations

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.value_objects import HostToken, LeagueId
from app.infrastructure.persistence.models.orm_models import LeagueORM
from app.infrastructure.persistence.mappers.player_mapper import player_to_domain
from app.infrastructure.persistence.mappers.team_mapper import team_to_domain


def league_to_domain(orm: LeagueORM) -> League:
    players = [player_to_domain(p) for p in orm.players]
    teams = [team_to_domain(t) for t in orm.teams]
    return League(
        league_id=LeagueId(value=orm.league_id),
        host_token=HostToken(value=orm.host_token),
        title=orm.title,
        description=orm.description,
        players=players,
        teams=teams,
        pending_deleted_team_ids=[],
    )


def league_to_orm(domain: League) -> LeagueORM:
    return LeagueORM(
        league_id=domain.league_id.value,
        title=domain.title,
        title_normalized=domain.title.lower().strip(),
        host_token=domain.host_token.value,
        description=domain.description,
    )
