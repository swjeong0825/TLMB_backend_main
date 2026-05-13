from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class AddAllowlistEntriesCommand:
    host_token: str
    league_id: str
    nicknames: list[str]


@dataclass
class AllowlistEntry:
    allowlist_entry_id: str
    nickname: str


@dataclass
class AddAllowlistEntriesResult:
    allowlist: list[AllowlistEntry]


class AddAllowlistEntriesUseCase:
    """Bulk-add nicknames to the league's allowlist.

    The use case is admin-gated; any duplicate (vs an existing allowlist
    nickname or another nickname inside the same batch) rejects the entire
    request via the aggregate (no partial inserts).
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: AddAllowlistEntriesCommand) -> AddAllowlistEntriesResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        new_entries = league.add_allowlist_entries(command.nicknames)
        await self._league_repo.save(league)

        return AddAllowlistEntriesResult(
            allowlist=[
                AllowlistEntry(
                    allowlist_entry_id=str(e.allowlist_entry_id.value),
                    nickname=e.nickname.value,
                )
                for e in new_entries
            ]
        )
