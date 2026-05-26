from __future__ import annotations

import uuid

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.value_objects import (
    HostEmail,
    HostToken,
    LeagueId,
    LeagueTimezone,
)
from app.infrastructure.persistence.models.orm_models import LeagueORM
from app.infrastructure.persistence.mappers.player_mapper import player_to_domain
from app.infrastructure.persistence.mappers.team_mapper import team_to_domain


def league_to_domain(
    orm: LeagueORM,
    match_counts_by_player: dict[uuid.UUID, int] | None = None,
) -> League:
    """Map a LeagueORM (with `players`, `teams` eagerly loaded) into a domain
    League aggregate.

    `match_counts_by_player` is an optional per-player participation count
    surfaced by the repository so `League.remove_player` can enforce the
    "zero participation" guard without an extra round-trip. When omitted,
    every player's `match_count` defaults to 0; that is safe for read paths
    (they ignore the field) and for write paths that don't call
    `remove_player`.
    """
    counts = match_counts_by_player or {}
    players = []
    for p in orm.players:
        player = player_to_domain(p)
        player.match_count = counts.get(p.player_id, 0)
        players.append(player)
    teams = [team_to_domain(t) for t in orm.teams]
    return League(
        league_id=LeagueId(value=orm.league_id),
        host_token=HostToken(value=orm.host_token),
        host_email=HostEmail(value=orm.host_email),
        league_timezone=LeagueTimezone(value=orm.league_timezone),
        latest_match_date=orm.latest_match_date,
        title=orm.title,
        description=orm.description,
        rules=LeagueRules.from_dict(orm.rules),
        players=players,
        teams=teams,
        pending_deleted_team_ids=[],
        pending_deleted_player_ids=[],
    )


def league_to_orm(domain: League) -> LeagueORM:
    return LeagueORM(
        league_id=domain.league_id.value,
        title=domain.title,
        title_normalized=domain.title.lower().strip(),
        host_token=domain.host_token.value,
        host_email=domain.host_email.value,
        league_timezone=domain.league_timezone.value,
        latest_match_date=domain.latest_match_date,
        description=domain.description,
        rules=domain.rules.to_dict(),
    )
