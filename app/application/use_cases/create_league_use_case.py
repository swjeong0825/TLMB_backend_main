from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.exceptions import LeagueTitleAlreadyExistsError


@dataclass
class CreateLeagueCommand:
    title: str
    description: str | None
    rules: dict[str, Any] | None = None
    allowlist: list[str] = field(default_factory=list)


@dataclass
class CreateLeagueResult:
    league_id: str
    host_token: str


class CreateLeagueUseCase:
    """Create a league and (optionally) seed its allowlist.

    When `command.allowlist` is non-empty, the use case populates the
    allowlist on the freshly-built aggregate before persisting. A single
    `repo.save(...)` then writes the league row and every allowlist-entry
    row through the same `AsyncSession`, so both reach the database in
    one transaction — partial state is impossible: any in-batch duplicate
    surfaces as `AllowlistNicknameAlreadyExistsError` from the aggregate
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
        league = League.create(command.title, command.description, host_token, rules=rules_vo)

        if command.allowlist:
            league.add_allowlist_entries(command.allowlist)

        await self._league_repo.save(league)

        return CreateLeagueResult(
            league_id=str(league.league_id.value),
            host_token=host_token,
        )
