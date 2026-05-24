from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class GetLeagueAdminInfoQuery:
    host_token: str
    league_id: str


@dataclass
class LeagueAdminInfoView:
    """Read model for admin-only league metadata (host-private fields).

    V1 exposes only ``host_email``. The type and ``GET /admin/leagues/{id}``
    route are intentionally general — see ``13_api_contracts.md`` →
    "Get League Admin Info (Admin)" → "Growth direction" before adding fields.
    """

    host_email: str


class GetLeagueAdminInfoUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: GetLeagueAdminInfoQuery) -> LeagueAdminInfoView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        if league.host_token.value != query.host_token:
            raise UnauthorizedError("Invalid host token")

        return LeagueAdminInfoView(host_email=str(league.host_email))
