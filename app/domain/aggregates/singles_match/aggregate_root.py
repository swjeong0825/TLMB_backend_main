from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId
from app.domain.exceptions import SamePlayerOnBothSidesError


@dataclass
class SinglesMatch:
    match_id: SinglesMatchId
    league_id: LeagueId
    player1_id: PlayerId
    player2_id: PlayerId
    set_score: SetScore
    created_at: datetime | None = None

    @classmethod
    def create(
        cls,
        league_id: LeagueId,
        player1_id: PlayerId,
        player2_id: PlayerId,
        set_score: SetScore,
    ) -> SinglesMatch:
        if player1_id == player2_id:
            raise SamePlayerOnBothSidesError(
                "player1_id and player2_id must be different players"
            )
        return cls(
            match_id=SinglesMatchId.generate(),
            league_id=league_id,
            player1_id=player1_id,
            player2_id=player2_id,
            set_score=set_score,
        )

    def edit_score(self, new_set_score: SetScore) -> None:
        self.set_score = new_set_score
