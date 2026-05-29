from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class RemovePlayerFromRosterCommand:
    host_token: str
    league_id: str
    player_id: str


class RemovePlayerFromRosterUseCase:
    """Remove a single pre-registered player from the league roster.

    Replaces the v5 `RemoveAllowlistEntryUseCase` with stricter semantics:
    the `Player` row is hard-deleted only when the player has zero pairs
    and zero matches. The aggregate enforces the guard (raises
    `PlayerHasParticipationError` with 409 semantics) — the repository
    has already populated `Player.match_count` at load time so the check
    is in-aggregate. Admin-gated.
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: RemovePlayerFromRosterCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        league.remove_player(command.player_id)
        await self._league_repo.save(league)
