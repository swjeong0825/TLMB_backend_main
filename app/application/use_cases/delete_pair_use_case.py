from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PairId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import (
    LeagueNotFoundError,
    PairHasMatchesError,
    PairNotFoundError,
    UnauthorizedError,
)


@dataclass
class DeletePairCommand:
    host_token: str
    league_id: str
    pair_id: str


class DeletePairUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, command: DeletePairCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        pair_id = PairId.from_str(command.pair_id)
        if not any(t.pair_id == pair_id for t in league.pairs):
            raise PairNotFoundError(f"Pair '{command.pair_id}' not found in this league")

        has_matches = await self._match_repo.has_matches_for_pair(pair_id, league_id)
        if has_matches:
            raise PairHasMatchesError(
                "This pair has associated match records; delete those matches first"
            )

        league.delete_pair(command.pair_id)
        await self._league_repo.save(league)
