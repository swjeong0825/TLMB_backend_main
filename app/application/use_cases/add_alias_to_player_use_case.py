from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class AddAliasToPlayerCommand:
    host_token: str
    league_id: str
    player_id: str
    alias: str


@dataclass
class PlayerAliasResult:
    player_id: str
    nickname: str
    aliases: list[str]


class AddAliasToPlayerUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: AddAliasToPlayerCommand) -> PlayerAliasResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        player = league.add_alias_to_player(command.player_id, command.alias)
        await self._league_repo.save(league)

        return PlayerAliasResult(
            player_id=str(player.player_id.value),
            nickname=player.canonical_nickname.value,
            aliases=[alias.value for alias in player.aliases],
        )
