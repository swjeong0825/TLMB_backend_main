from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class RemoveAllowlistEntryCommand:
    host_token: str
    league_id: str
    allowlist_entry_id: str


class RemoveAllowlistEntryUseCase:
    """Remove a single nickname from the league's allowlist.

    Does NOT delete any roster `Player` row — the allowlist and the roster
    are decoupled by design (see
    `Design_Doc/TLMB_Design_doc/20_allowlist.md`).
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: RemoveAllowlistEntryCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        league.remove_allowlist_entry(command.allowlist_entry_id)
        await self._league_repo.save(league)
