from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class EditPlayerNicknameCommand:
    host_token: str
    league_id: str
    player_id: str
    new_nickname: str


@dataclass
class UpdatedPlayerResult:
    player_id: str
    new_nickname: str


class EditPlayerNicknameUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: EditPlayerNicknameCommand) -> UpdatedPlayerResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        updated_player = league.edit_player_nickname(command.player_id, command.new_nickname)
        await self._league_repo.save(league)

        return UpdatedPlayerResult(
            player_id=str(updated_player.player_id.value),
            new_nickname=updated_player.nickname.value,
        )
