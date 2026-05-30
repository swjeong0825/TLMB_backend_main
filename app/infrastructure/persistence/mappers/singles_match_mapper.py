from __future__ import annotations

from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId
from app.infrastructure.persistence.models.orm_models import SinglesMatchORM


def singles_match_to_domain(orm: SinglesMatchORM) -> SinglesMatch:
    return SinglesMatch(
        match_id=SinglesMatchId(value=orm.match_id),
        league_id=LeagueId(value=orm.league_id),
        player1_id=PlayerId(value=orm.player1_id),
        player2_id=PlayerId(value=orm.player2_id),
        set_score=SetScore(
            pair1_score=orm.player1_score,
            pair2_score=orm.player2_score,
        ),
        created_at=orm.created_at,
    )


def singles_match_to_orm(domain: SinglesMatch) -> SinglesMatchORM:
    return SinglesMatchORM(
        match_id=domain.match_id.value,
        league_id=domain.league_id.value,
        player1_id=domain.player1_id.value,
        player2_id=domain.player2_id.value,
        player1_score=domain.set_score.pair1_score,
        player2_score=domain.set_score.pair2_score,
    )
