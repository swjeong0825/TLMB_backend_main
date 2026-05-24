from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.match.value_objects import MatchId, SetScore
from app.domain.exceptions import (
    LeagueNotFoundError,
    MatchEditWindowExpiredError,
    MatchNotFoundError,
    UnauthorizedError,
)


@dataclass
class EditMatchScoreCommand:
    """Command for editing a match score.

    `host_token` is optional:

    - If set, the caller is treated as the admin: the token must match
      the league's `host_token` (401 on mismatch) and there is **no**
      time-window gate.
    - If `None`, the caller is treated as a player: no auth check, but
      the match must have been created within the last
      `window_seconds` (raises `MatchEditWindowExpiredError` otherwise).

    This mirrors the existing trust model: anyone with `league_id` can
    submit a match (`POST /leagues/{id}/matches`), so anyone can also
    correct a *recent* match's score; only the host can correct an old
    one.
    """

    host_token: str | None
    league_id: str
    match_id: str
    team1_score: str
    team2_score: str


@dataclass
class UpdatedMatchResult:
    match_id: str
    team1_score: str
    team2_score: str


class EditMatchScoreUseCase:
    """Edit a match's score.

    `window_seconds` is the player-edit window: a non-admin caller can
    only edit a match within this many seconds of its `created_at`.
    Admin (`host_token` provided) bypasses the window. The value is
    injected (defaults to 3600) so tests can shrink/expand it without
    monkeypatching `datetime.now`.

    The window check is enforced here at the application layer (not on
    `Match`) because the threshold is a deployment-level policy and
    needs `datetime.now` — both things the pure-domain aggregate cannot
    touch without leaking infrastructure concerns. See
    `Design_Doc/TLMB_Design_doc/05_aggregate_designs/match.md` and
    `harness_notes/01_when_to_extract_a_policy.md`.
    """

    DEFAULT_WINDOW_SECONDS = 3600

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

    async def execute(self, command: EditMatchScoreCommand) -> UpdatedMatchResult:
        league_id = LeagueId.from_str(command.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{command.league_id}' not found")

        is_admin = command.host_token is not None
        if is_admin and league.host_token.value != command.host_token:
            raise UnauthorizedError("Invalid host token")

        new_set_score = SetScore(
            team1_score=command.team1_score, team2_score=command.team2_score
        )

        match_id = MatchId.from_str(command.match_id)
        match = await self._match_repo.get_by_id(match_id, league_id)
        if match is None:
            raise MatchNotFoundError(f"Match '{command.match_id}' not found in this league")

        if not is_admin:
            self._enforce_player_edit_window(match.created_at, command.match_id)

        match.edit_score(new_set_score)
        await self._match_repo.save(match)

        return UpdatedMatchResult(
            match_id=str(match.match_id.value),
            team1_score=match.set_score.team1_score,
            team2_score=match.set_score.team2_score,
        )

    def _enforce_player_edit_window(
        self, created_at: datetime | None, match_id: str
    ) -> None:
        # `created_at` is set by the DB on insert and re-populated on
        # `match_to_domain`. A persisted match always has it; if it's
        # somehow absent (e.g. a non-persisted aggregate slipped through),
        # we conservatively reject the edit rather than allow it.
        if created_at is None:
            raise MatchEditWindowExpiredError(
                "Match has no recorded creation time; only the league host can edit it.",
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
            raise MatchEditWindowExpiredError(
                (
                    f"This match was recorded {age_seconds} seconds ago, which is "
                    f"past the {self._window_seconds}-second player-edit window. "
                    "Only the league host can edit it now."
                ),
                match_id=match_id,
                window_seconds=self._window_seconds,
                age_seconds=age_seconds,
            )
