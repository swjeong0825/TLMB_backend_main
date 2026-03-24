from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, TeamId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import (
    LeagueNotFoundError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)


@dataclass
class DeleteTeamCommand:
    host_token: str
    league_id: str
    team_id: str


class DeleteTeamUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, command: DeleteTeamCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        team_id = TeamId.from_str(command.team_id)
        if not any(t.team_id == team_id for t in league.teams):
            raise TeamNotFoundError(f"Team '{command.team_id}' not found in this league")

        has_matches = await self._match_repo.has_matches_for_team(team_id, league_id)
        if has_matches:
            raise TeamHasMatchesError(
                "This team has associated match records; delete those matches first"
            )

        league.delete_team(command.team_id)
        await self._league_repo.save(league)
