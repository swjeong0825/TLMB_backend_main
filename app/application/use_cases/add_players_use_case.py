from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class AddPlayersCommand:
    host_token: str
    league_id: str
    nicknames: list[str]
    ratings: list[float | None] | None = None


@dataclass
class PlayerEntry:
    player_id: str
    nickname: str
    rating: float | None = None


@dataclass
class AddPlayersResult:
    players: list[PlayerEntry]


class AddPlayersUseCase:
    """Bulk-add pre-registered players directly to the league roster.

    Replaces the v5 `AddAllowlistEntriesUseCase`: writes `Player` rows
    directly (no allowlist side table). Any duplicate (vs an existing roster
    nickname or another nickname inside the same batch) rejects the entire
    request via the aggregate (no partial inserts). Admin-gated.
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: AddPlayersCommand) -> AddPlayersResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        new_players = league.add_players(command.nicknames, command.ratings)
        await self._league_repo.save(league)

        return AddPlayersResult(
            players=[
                PlayerEntry(
                    player_id=str(p.player_id.value),
                    nickname=p.nickname.value,
                    rating=p.rating,
                )
                for p in new_players
            ]
        )
