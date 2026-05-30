from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.use_cases.league_day import league_local_day_utc_bounds
from app.application.unit_of_work.submit_match_result_uow import SubmitMatchResultUnitOfWork
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.exceptions import (
    DuplicatePairMatchupMatchError,
    LeagueNotFoundError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
)


@dataclass
class SubmitMatchResultCommand:
    league_id: str
    pair1_nicknames: tuple[str, str]
    pair2_nicknames: tuple[str, str]
    pair1_score: str
    pair2_score: str


@dataclass
class SubmitMatchResultResult:
    match_id: str
    created_at: datetime


class SubmitMatchResultUseCase:
    def __init__(self, uow_factory: type[SubmitMatchResultUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, command: SubmitMatchResultCommand) -> SubmitMatchResultResult:
        pair1_nickname1 = command.pair1_nicknames[0].lower().strip()
        pair1_nickname2 = command.pair1_nicknames[1].lower().strip()
        pair2_nickname1 = command.pair2_nicknames[0].lower().strip()
        pair2_nickname2 = command.pair2_nicknames[1].lower().strip()

        if pair1_nickname1 == pair1_nickname2:
            raise SamePlayerWithinSinglePairError(
                "Pair 1 has the same player listed twice"
            )
        if pair2_nickname1 == pair2_nickname2:
            raise SamePlayerWithinSinglePairError(
                "Pair 2 has the same player listed twice"
            )

        if {pair1_nickname1, pair1_nickname2} & {pair2_nickname1, pair2_nickname2}:
            raise SamePlayerOnBothPairsError(
                "The same player appears on both pairs"
            )

        set_score = SetScore(pair1_score=command.pair1_score, pair2_score=command.pair2_score)

        async with self._uow_factory() as uow:
            league_id = LeagueId.from_str(command.league_id)
            league = await uow.league_repo.get_by_id_with_lock(league_id)
            if league is None:
                raise LeagueNotFoundError(f"League '{command.league_id}' not found")

            league.validate_match_participants_on_roster(
                [pair1_nickname1, pair1_nickname2, pair2_nickname1, pair2_nickname2]
            )

            _, pair1 = league.register_players_and_pair(
                pair1_nickname1, pair1_nickname2
            )
            _, pair2 = league.register_players_and_pair(
                pair2_nickname1, pair2_nickname2
            )
            league.validate_pairs_do_not_share_players(pair1, pair2)

            if league.rules.pair_matchup_idempotency == "once_per_league":
                pair_exists = await uow.match_repo.exists_match_for_pair_matchup(
                    league_id, pair1.pair_id, pair2.pair_id
                )
                if pair_exists:
                    raise DuplicatePairMatchupMatchError(
                        "A match between these two pairs already exists in this league"
                    )
            elif league.rules.pair_matchup_idempotency == "once_per_day":
                now_utc = datetime.now(timezone.utc)
                day_start_utc, next_day_start_utc = league_local_day_utc_bounds(
                    now_utc, league.league_timezone.value
                )
                pair_exists = await uow.match_repo.exists_match_for_pair_matchup_between(
                    league_id,
                    pair1.pair_id,
                    pair2.pair_id,
                    day_start_utc,
                    next_day_start_utc,
                )
                if pair_exists:
                    raise DuplicatePairMatchupMatchError(
                        "A match between these two pairs already exists today"
                    )

            match = Match.create(league_id, pair1.pair_id, pair2.pair_id, set_score)

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
