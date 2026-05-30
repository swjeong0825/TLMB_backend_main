from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository
from app.domain.aggregates.singles_match.value_objects import SinglesMatchId
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchDeleteWindowExpiredError,
    MatchNotFoundError,
    UnauthorizedError,
)


@dataclass
class DeleteSinglesMatchCommand:
    host_token: str | None
    league_id: str
    match_id: str


class DeleteSinglesMatchUseCase:
    DEFAULT_WINDOW_SECONDS = 600

    def __init__(
        self,
        league_repo: LeagueRepository,
        singles_match_repo: SinglesMatchRepository,
        window_seconds: int | None = None,
    ) -> None:
        self._league_repo = league_repo
        self._singles_match_repo = singles_match_repo
        self._window_seconds = (
            window_seconds
            if window_seconds is not None
            else self.DEFAULT_WINDOW_SECONDS
        )

    async def execute(self, command: DeleteSinglesMatchCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id_with_lock(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        is_admin = command.host_token is not None
        if is_admin and league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        match_id = SinglesMatchId.from_str(command.match_id)
        match = await self._singles_match_repo.get_by_id(match_id, league_id)
        if match is None:
            raise MatchNotFoundError(
                f"Singles match '{command.match_id}' not found in this league"
            )

        if not is_admin:
            self._enforce_player_delete_window(match.created_at, command.match_id)

        await self._singles_match_repo.delete(match_id, league_id)
        latest_match = await self._singles_match_repo.get_latest_by_league(league_id)
        league.reset_latest_singles_match_date(
            latest_match.created_at if latest_match is not None else None
        )
        await self._league_repo.save(league)

    def _enforce_player_delete_window(
        self, created_at: datetime | None, match_id: str
    ) -> None:
        if created_at is None:
            raise MatchDeleteWindowExpiredError(
                "Match has no recorded creation time; only the league host can delete it.",
                match_id=match_id,
                window_seconds=self._window_seconds,
                age_seconds=-1,
            )

        now = datetime.now(timezone.utc)
        delta_seconds = (now - created_at).total_seconds()
        age_seconds = int(delta_seconds)
        if delta_seconds > self._window_seconds:
            raise MatchDeleteWindowExpiredError(
                (
                    f"This match was recorded {age_seconds} seconds ago, which is "
                    f"past the {self._window_seconds}-second player-delete window. "
                    "Only the league host can delete it now."
                ),
                match_id=match_id,
                window_seconds=self._window_seconds,
                age_seconds=age_seconds,
            )
