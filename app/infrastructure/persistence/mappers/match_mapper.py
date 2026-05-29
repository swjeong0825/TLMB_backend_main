from __future__ import annotations

from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.infrastructure.persistence.models.orm_models import MatchORM


def match_to_domain(orm: MatchORM) -> Match:
    return Match(
        match_id=MatchId(value=orm.match_id),
        league_id=LeagueId(value=orm.league_id),
        pair1_id=PairId(value=orm.pair1_id),
        pair2_id=PairId(value=orm.pair2_id),
        set_score=SetScore(pair1_score=orm.pair1_score, pair2_score=orm.pair2_score),
        created_at=orm.created_at,
    )


def match_to_orm(domain: Match) -> MatchORM:
    return MatchORM(
        match_id=domain.match_id.value,
        league_id=domain.league_id.value,
        pair1_id=domain.pair1_id.value,
        pair2_id=domain.pair2_id.value,
        pair1_score=domain.set_score.pair1_score,
        pair2_score=domain.set_score.pair2_score,
    )
