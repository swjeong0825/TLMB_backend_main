from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.match.value_objects import MatchId
from app.domain.exceptions import LeagueNotFoundError, MatchNotFoundError, UnauthorizedError


@dataclass
class DeleteMatchCommand:
    host_token: str
    league_id: str
    match_id: str


class DeleteMatchUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, command: DeleteMatchCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        match_id = MatchId.from_str(command.match_id)
        match = await self._match_repo.get_by_id(match_id, league_id)
        if match is None:
            raise MatchNotFoundError(f"Match '{command.match_id}' not found in this league")

        await self._match_repo.delete(match_id, league_id)
