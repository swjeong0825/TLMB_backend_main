from __future__ import annotations

from app.domain.aggregates.league.entities import Team
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, TeamId
from app.infrastructure.persistence.models.orm_models import TeamORM


def team_to_domain(orm: TeamORM) -> Team:
    return Team(
        team_id=TeamId(value=orm.team_id),
        player_id_1=PlayerId(value=orm.player_id_1),
        player_id_2=PlayerId(value=orm.player_id_2),
    )


def team_to_orm(domain: Team, league_id: LeagueId) -> TeamORM:
    return TeamORM(
        team_id=domain.team_id.value,
        league_id=league_id.value,
        player_id_1=domain.player_id_1.value,
        player_id_2=domain.player_id_2.value,
    )
