from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, UnauthorizedError


@dataclass
class AddEligiblePlayersCommand:
    host_token: str
    league_id: str
    nicknames: list[str]


@dataclass
class EligiblePlayerEntry:
    eligible_player_id: str
    nickname: str


@dataclass
class AddEligiblePlayersResult:
    eligible_players: list[EligiblePlayerEntry]


class AddEligiblePlayersUseCase:
    """Bulk-add nicknames to the league's eligible-players allowlist.

    The use case is admin-gated; any duplicate (vs an existing eligible
    nickname or another nickname inside the same batch) rejects the entire
    request via the aggregate (no partial inserts).
    """

    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, command: AddEligiblePlayersCommand) -> AddEligiblePlayersResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        if league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        new_entries = league.add_eligible_players(command.nicknames)
        await self._league_repo.save(league)

        return AddEligiblePlayersResult(
            eligible_players=[
                EligiblePlayerEntry(
                    eligible_player_id=str(e.eligible_player_id.value),
                    nickname=e.nickname.value,
                )
                for e in new_entries
            ]
        )
