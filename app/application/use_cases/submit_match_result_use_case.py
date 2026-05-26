from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.application.unit_of_work.submit_match_result_uow import SubmitMatchResultUnitOfWork
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.exceptions import (
    DuplicateTeamPairMatchError,
    LeagueNotFoundError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
)


@dataclass
class SubmitMatchResultCommand:
    league_id: str
    team1_nicknames: tuple[str, str]
    team2_nicknames: tuple[str, str]
    team1_score: str
    team2_score: str


@dataclass
class SubmitMatchResultResult:
    match_id: str
    created_at: datetime


def _league_local_day_utc_bounds(
    now_utc: datetime, league_timezone: str
) -> tuple[datetime, datetime]:
    tz = ZoneInfo(league_timezone)
    local_day = now_utc.astimezone(tz).date()
    start_local = datetime.combine(local_day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


class SubmitMatchResultUseCase:
    def __init__(self, uow_factory: type[SubmitMatchResultUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: SubmitMatchResultCommand) -> SubmitMatchResultResult:
        t1_n1 = command.team1_nicknames[0].lower().strip()
        t1_n2 = command.team1_nicknames[1].lower().strip()
        t2_n1 = command.team2_nicknames[0].lower().strip()
        t2_n2 = command.team2_nicknames[1].lower().strip()

        if t1_n1 == t1_n2:
            raise SamePlayerWithinSingleTeamError(
                "Team 1 has the same player listed twice"
            )
        if t2_n1 == t2_n2:
            raise SamePlayerWithinSingleTeamError(
                "Team 2 has the same player listed twice"
            )

        if {t1_n1, t1_n2} & {t2_n1, t2_n2}:
            raise SamePlayerOnBothTeamsError(
                "The same player appears on both teams"
            )

        set_score = SetScore(team1_score=command.team1_score, team2_score=command.team2_score)

        async with self._uow_factory() as uow:
            league_id = LeagueId.from_str(command.league_id)
            league = await uow.league_repo.get_by_id_with_lock(league_id)
            if league is None:
                raise LeagueNotFoundError(f"League '{command.league_id}' not found")

            league.validate_match_participants_on_roster([t1_n1, t1_n2, t2_n1, t2_n2])

            _, team1 = league.register_players_and_team(t1_n1, t1_n2)
            _, team2 = league.register_players_and_team(t2_n1, t2_n2)
            league.validate_teams_do_not_share_players(team1, team2)

            if league.rules.match_pair_idempotency == "once_per_league":
                pair_exists = await uow.match_repo.exists_match_for_team_pair(
                    league_id, team1.team_id, team2.team_id
                )
                if pair_exists:
                    raise DuplicateTeamPairMatchError(
                        "A match between these two teams already exists in this league"
                    )
            elif league.rules.match_pair_idempotency == "once_per_day":
                now_utc = datetime.now(timezone.utc)
                day_start_utc, next_day_start_utc = _league_local_day_utc_bounds(
                    now_utc, league.league_timezone.value
                )
                pair_exists = await uow.match_repo.exists_match_for_team_pair_between(
                    league_id,
                    team1.team_id,
                    team2.team_id,
                    day_start_utc,
                    next_day_start_utc,
                )
                if pair_exists:
                    raise DuplicateTeamPairMatchError(
                        "A match between these two teams already exists today"
                    )

            match = Match.create(league_id, team1.team_id, team2.team_id, set_score)

            await uow.league_repo.save(league)
            await uow.match_repo.save(match)
            # `match.created_at` is populated by the repo on insert via flush.
            # If somehow missing (e.g. a non-persisting repo fake in a test),
            # fall back to current UTC so callers always have a non-null value.
            created_at = match.created_at or datetime.now(timezone.utc)
            league.note_match_recorded_at(created_at)
            await uow.league_repo.save(league)
            await uow.commit()

        return SubmitMatchResultResult(
            match_id=str(match.match_id.value),
            created_at=created_at,
        )
