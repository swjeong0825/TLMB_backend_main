from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.match.value_objects import MatchId
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchDeleteWindowExpiredError,
    MatchNotFoundError,
    UnauthorizedError,
)


@dataclass
class DeleteMatchCommand:
    """Command for deleting a match.

    `host_token` is optional:

    - If set, the caller is treated as the admin: the token must match
      the league's `host_token` (401 on mismatch) and there is **no**
      time-window gate.
    - If `None`, the caller is treated as a player: no auth check, but
      the match must have been created within the last
      `window_seconds` (raises `MatchDeleteWindowExpiredError`
      otherwise).

    Mirrors `EditMatchScoreCommand`'s trust model: anyone with
    `league_id` can submit a match, so anyone can also delete one they
    just submitted while it is still fresh; only the host can delete
    older matches.
    """

    host_token: str | None
    league_id: str
    match_id: str


class DeleteMatchUseCase:
    """Delete a match.

    `window_seconds` is the player-delete window: a non-admin caller
    can only delete a match within this many seconds of its
    `created_at`. Admin (`host_token` provided) bypasses the window.
    The value is injected (defaults to 600s / 10 min) so tests can
    shrink/expand it without monkeypatching `datetime.now`.

    Mirrors `EditMatchScoreUseCase`. The window check is enforced here
    at the application layer (not on `Match`) because the threshold is
    a deployment-level policy and needs `datetime.now` — both things
    the pure-domain aggregate cannot touch without leaking
    infrastructure concerns. See
    `Design_Doc/TLMB_Design_doc/05_aggregate_designs/match.md` and
    `harness_notes/01_when_to_extract_a_policy.md`.
    """

    DEFAULT_WINDOW_SECONDS = 600

    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
        window_seconds: int | None = None,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._window_seconds = (
            window_seconds
            if window_seconds is not None
            else self.DEFAULT_WINDOW_SECONDS
        )

    async def execute(self, command: DeleteMatchCommand) -> None:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        is_admin = command.host_token is not None
        if is_admin and league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        match_id = MatchId.from_str(command.match_id)
        match = await self._match_repo.get_by_id(match_id, league_id)
        if match is None:
            raise MatchNotFoundError(f"Match '{command.match_id}' not found in this league")

        if not is_admin:
            self._enforce_player_delete_window(match.created_at, command.match_id)

        await self._match_repo.delete(match_id, league_id)

    def _enforce_player_delete_window(
        self, created_at: datetime | None, match_id: str
    ) -> None:
        # `created_at` is set by the DB on insert and re-populated on
        # `match_to_domain`. A persisted match always has it; if it's
        # somehow absent (e.g. a non-persisted aggregate slipped through),
        # we conservatively reject the delete rather than allow it.
        if created_at is None:
            raise MatchDeleteWindowExpiredError(
                "Match has no recorded creation time; only the league host can delete it.",
                match_id=match_id,
                window_seconds=self._window_seconds,
                age_seconds=-1,
            )

        now = datetime.now(timezone.utc)
        delta = now - created_at
        # Compare in raw seconds (float) so a sub-second-old match still
        # trips a `window_seconds=0` gate. `age_seconds` is rounded to int
        # only for the exception payload, where a fractional age would be
        # noise.
        delta_seconds = delta.total_seconds()
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
