from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.exceptions import LeagueTitleAlreadyExistsError


@dataclass
class CreateLeagueCommand:
    title: str
    description: str | None


@dataclass
class CreateLeagueResult:
    league_id: str
    host_token: str


class CreateLeagueUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: CreateLeagueCommand) -> CreateLeagueResult:
        normalized_title = command.title.lower().strip()

        existing = await self._league_repo.get_by_normalized_title(normalized_title)
        if existing is not None:
            raise LeagueTitleAlreadyExistsError(
                f"A league with the title '{command.title}' already exists"
            )

        host_token = str(uuid.uuid4())
        league = League.create(command.title, command.description, host_token)
        await self._league_repo.save(league)

        return CreateLeagueResult(
            league_id=str(league.league_id.value),
            host_token=host_token,
        )
