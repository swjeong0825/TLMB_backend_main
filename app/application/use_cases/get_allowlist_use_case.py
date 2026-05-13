from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError


@dataclass
class GetAllowlistQuery:
    league_id: str


@dataclass
class AllowlistEntry:
    allowlist_entry_id: str
    nickname: str


@dataclass
class AllowlistView:
    allowlist: list[AllowlistEntry]


class GetAllowlistUseCase:
    """Read the host-curated allowlist.

    Public read (league_id only) — mirrors `GetLeagueRosterUseCase`. Sorted
    alphabetically by nickname for stable display ordering.
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: GetAllowlistQuery) -> AllowlistView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        entries = sorted(
            [
                AllowlistEntry(
                    allowlist_entry_id=str(entry.allowlist_entry_id.value),
                    nickname=entry.nickname.value,
                )
                for entry in league.allowlist
            ],
            key=lambda e: e.nickname,
        )

        return AllowlistView(allowlist=entries)
