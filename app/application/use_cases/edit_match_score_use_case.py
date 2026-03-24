from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import LeagueNotFoundError, MatchNotFoundError, UnauthorizedError


@dataclass
class EditMatchScoreCommand:
    host_token: str
    league_id: str
    match_id: str
    team1_score: str
    team2_score: str


@dataclass
class UpdatedMatchResult:
    match_id: str
    team1_score: str
    team2_score: str


class EditMatchScoreUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, command: EditMatchScoreCommand) -> UpdatedMatchResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        new_set_score = SetScore(
            team1_score=command.team1_score, team2_score=command.team2_score
        )

        match_id = MatchId.from_str(command.match_id)
        match = await self._match_repo.get_by_id(match_id, league_id)
        if match is None:
            raise MatchNotFoundError(f"Match '{command.match_id}' not found in this league")

        match.edit_score(new_set_score)
        await self._match_repo.save(match)

        return UpdatedMatchResult(
            match_id=str(match.match_id.value),
            team1_score=match.set_score.team1_score,
            team2_score=match.set_score.team2_score,
        )
