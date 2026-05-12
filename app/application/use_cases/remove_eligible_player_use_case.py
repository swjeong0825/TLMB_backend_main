from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class RemoveEligiblePlayerCommand:
    host_token: str
    league_id: str
    eligible_player_id: str


class RemoveEligiblePlayerUseCase:
    """Remove a single nickname from the eligible-players allowlist.

    Does NOT delete any roster `Player` row — the eligible list and the
    roster are decoupled by design (see
    `Design_Doc/TLMB_Design_doc/20_eligible_players.md`).
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: RemoveEligiblePlayerCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        league.remove_eligible_player(command.eligible_player_id)
        await self._league_repo.save(league)
