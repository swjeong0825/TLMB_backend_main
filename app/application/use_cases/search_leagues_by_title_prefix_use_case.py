from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository


@dataclass
class SearchLeaguesByTitlePrefixQuery:
    """title_prefix_normalized must be non-empty (strip + lower), enforced at API layer."""

    title_prefix_normalized: str
    limit: int


@dataclass(frozen=True)
class LeagueListItem:
    league_id: str
    title: str


class SearchLeaguesByTitlePrefixUseCase:
    DEFAULT_LIMIT = 50
    MAX_LIMIT = 100

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: SearchLeaguesByTitlePrefixQuery) -> list[LeagueListItem]:
        effective_limit = min(max(query.limit, 1), self.MAX_LIMIT)
        rows = await self._league_repo.search_by_title_prefix(
            query.title_prefix_normalized,
            effective_limit,
        )
        return [LeagueListItem(league_id=lid, title=title) for lid, title in rows]
