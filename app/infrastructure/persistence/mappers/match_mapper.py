from __future__ import annotations

from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.infrastructure.persistence.models.orm_models import MatchORM


def match_to_domain(orm: MatchORM) -> Match:
    return Match(
        match_id=MatchId(value=orm.match_id),
        league_id=LeagueId(value=orm.league_id),
        team1_id=TeamId(value=orm.team1_id),
        team2_id=TeamId(value=orm.team2_id),
        set_score=SetScore(team1_score=orm.team1_score, team2_score=orm.team2_score),
        created_at=orm.created_at,
    )


def match_to_orm(domain: Match) -> MatchORM:
    return MatchORM(
        match_id=domain.match_id.value,
        league_id=domain.league_id.value,
        team1_id=domain.team1_id.value,
        team2_id=domain.team2_id.value,
        team1_score=domain.set_score.team1_score,
        team2_score=domain.set_score.team2_score,
    )
