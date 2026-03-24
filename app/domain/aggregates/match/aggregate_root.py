from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import SameTeamOnBothSidesError


@dataclass
class Match:
    match_id: MatchId
    league_id: LeagueId
    team1_id: TeamId
    team2_id: TeamId
    set_score: SetScore
    created_at: datetime | None = None

    @classmethod
    def create(
        cls,
        league_id: LeagueId,
        team1_id: TeamId,
        team2_id: TeamId,
        set_score: SetScore,
    ) -> Match:
        if team1_id == team2_id:
            raise SameTeamOnBothSidesError("team1_id and team2_id must be different teams")
        return cls(
            match_id=MatchId.generate(),
            league_id=league_id,
            team1_id=team1_id,
            team2_id=team2_id,
            set_score=set_score,
        )

    def edit_score(self, new_set_score: SetScore) -> None:
        self.set_score = new_set_score
