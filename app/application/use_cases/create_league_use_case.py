from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import DEFAULT_LEAGUE_TIMEZONE
from app.domain.exceptions import LeagueTitleAlreadyExistsError


@dataclass
class CreateLeagueCommand:
    title: str
    host_email: str
    description: str | None = None
    league_timezone: str = DEFAULT_LEAGUE_TIMEZONE
    rules: dict[str, Any] | None = None
    initial_players: list[str] = field(default_factory=list)


@dataclass
class CreateLeagueResult:
    league_id: str
    host_token: str


class CreateLeagueUseCase:
    """Create a league and (optionally) seed its roster with pre-registered players.

    When `command.initial_players` is non-empty, the use case adds each
    nickname to the freshly-built aggregate via `League.add_players` before
    persisting. A single `repo.save(...)` then writes the league row and
    every player row through the same `AsyncSession`, so both reach the
    database in one transaction — partial state is impossible: any in-batch
    duplicate surfaces as `NicknameAlreadyInUseError` from the aggregate
    before `save` runs.
    """

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
        rules_vo = (
            LeagueRules.from_dict(command.rules) if command.rules is not None else None
        )
        league = League.create(
            command.title,
            command.description,
            host_token,
            host_email=command.host_email,
            league_timezone=command.league_timezone,
            rules=rules_vo,
        )

        if command.initial_players:
            league.add_players(command.initial_players)

        await self._league_repo.save(league)

        return CreateLeagueResult(
            league_id=str(league.league_id.value),
            host_token=host_token,
        )
