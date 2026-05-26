from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases.add_alias_to_player_use_case import PlayerAliasResult
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class RemoveAliasFromPlayerCommand:
    host_token: str
    league_id: str
    player_id: str
    alias: str


class RemoveAliasFromPlayerUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: RemoveAliasFromPlayerCommand) -> PlayerAliasResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        player = league.remove_alias_from_player(command.player_id, command.alias)
        await self._league_repo.save(league)

        return PlayerAliasResult(
            player_id=str(player.player_id.value),
            nickname=player.canonical_nickname.value,
            aliases=[alias.value for alias in player.aliases],
        )
