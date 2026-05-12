from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError


@dataclass
class GetEligiblePlayersQuery:
    league_id: str


@dataclass
class EligiblePlayerEntry:
    eligible_player_id: str
    nickname: str


@dataclass
class EligiblePlayersView:
    eligible_players: list[EligiblePlayerEntry]


class GetEligiblePlayersUseCase:
    """Read the host-curated eligible-players allowlist.

    Public read (league_id only) — mirrors `GetLeagueRosterUseCase`. Sorted
    alphabetically by nickname for stable display ordering.
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: GetEligiblePlayersQuery) -> EligiblePlayersView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        entries = sorted(
            [
                EligiblePlayerEntry(
                    eligible_player_id=str(ep.eligible_player_id.value),
                    nickname=ep.nickname.value,
                )
                for ep in league.eligible_players
            ],
            key=lambda e: e.nickname,
        )

        return EligiblePlayersView(eligible_players=entries)
