from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import SamePairOnBothSidesError


@dataclass
class Match:
    match_id: MatchId
    league_id: LeagueId
    pair1_id: PairId
    pair2_id: PairId
    set_score: SetScore
    created_at: datetime | None = None

    @classmethod
    def create(
        cls,
        league_id: LeagueId,
        pair1_id: PairId,
        pair2_id: PairId,
        set_score: SetScore,
    ) -> Match:
        if pair1_id == pair2_id:
            raise SamePairOnBothSidesError("pair1_id and pair2_id must be different pairs")
        return cls(
            match_id=MatchId.generate(),
            league_id=league_id,
            pair1_id=pair1_id,
            pair2_id=pair2_id,
            set_score=set_score,
        )

    def edit_score(self, new_set_score: SetScore) -> None:
        self.set_score = new_set_score
