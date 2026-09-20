from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.application.unit_of_work.submit_singles_match_result_uow import (
    SubmitSinglesMatchResultUnitOfWork,
)
from app.application.use_cases.league_day import league_local_day_utc_bounds
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.exceptions import (
    DuplicateSinglesMatchupMatchError,
    LeagueNotFoundError,
    PlannedMatchNotFoundError,
    SamePlayerOnBothSidesError,
)


@dataclass
class SubmitSinglesMatchResultCommand:
    league_id: str
    player1_nickname: str
    player2_nickname: str
    player1_score: str
    player2_score: str
    planned_match_id: UUID | None = None


@dataclass
class SubmitSinglesMatchResultResult:
    match_id: str
    created_at: datetime


class SubmitSinglesMatchResultUseCase:
    def __init__(
        self, uow_factory: type[SubmitSinglesMatchResultUnitOfWork]
    ) -> None:
        self._uow_factory = uow_factory

    async def execute(
        self, command: SubmitSinglesMatchResultCommand
    ) -> SubmitSinglesMatchResultResult:
        # Preserve early validation for manual submissions; planned submissions
        # must resolve their pending plan before applying recording rules.
        validated = self._validate_result(command) if command.planned_match_id is None else None

        async with self._uow_factory() as uow:
            league_id = LeagueId.from_str(command.league_id)
            league = await uow.league_repo.get_by_id_with_lock(league_id)
            if league is None:
                raise LeagueNotFoundError(f"League '{command.league_id}' not found")

            if command.planned_match_id is not None:
                plan = await uow.planned_match_repo.get_by_id_with_lock(
                    league_id, command.planned_match_id
                )
                if plan is None:
                    raise PlannedMatchNotFoundError(
                        f"Planned match '{command.planned_match_id}' not found in this league"
                    )
                plan.value.validate_participants(
                    (command.player1_nickname,), (command.player2_nickname,)
                )

            player1_nickname, player2_nickname, set_score = validated or self._validate_result(command)

            league.validate_match_participants_on_roster(
                [player1_nickname, player2_nickname]
            )
            player1 = league.register_single_player(player1_nickname)
            player2 = league.register_single_player(player2_nickname)
            if player1.player_id == player2.player_id:
                raise SamePlayerOnBothSidesError(
                    "Both nicknames resolve to the same player"
                )

            if league.rules.pair_matchup_idempotency == "once_per_league":
                match_exists = (
                    await uow.singles_match_repo.exists_match_for_player_matchup(
                        league_id, player1.player_id, player2.player_id
                    )
                )
                if match_exists:
                    raise DuplicateSinglesMatchupMatchError(
                        "A singles match between these two players already exists in this league"
                    )
            elif league.rules.pair_matchup_idempotency == "once_per_day":
                now_utc = datetime.now(timezone.utc)
                day_start_utc, next_day_start_utc = league_local_day_utc_bounds(
                    now_utc, league.league_timezone.value
                )
                match_exists = (
                    await uow.singles_match_repo.exists_match_for_player_matchup_between(
                        league_id,
                        player1.player_id,
                        player2.player_id,
                        day_start_utc,
                        next_day_start_utc,
                    )
                )
                if match_exists:
                    raise DuplicateSinglesMatchupMatchError(
                        "A singles match between these two players already exists today"
                    )

            match = SinglesMatch.create(
                league_id,
                player1.player_id,
                player2.player_id,
                set_score,
            )

            await uow.league_repo.save(league)
            await uow.singles_match_repo.save(match)
            created_at = match.created_at or datetime.now(timezone.utc)
            league.note_singles_match_recorded_at(created_at)
            await uow.league_repo.save(league)
            if command.planned_match_id is not None:
                await uow.planned_match_repo.delete(league_id, command.planned_match_id)
            await uow.commit()

        return SubmitSinglesMatchResultResult(
            match_id=str(match.match_id.value),
            created_at=created_at,
        )

    @staticmethod
    def _validate_result(
        command: SubmitSinglesMatchResultCommand,
    ) -> tuple[str, str, SetScore]:
        player1_nickname = PlayerNickname(command.player1_nickname).value
        player2_nickname = PlayerNickname(command.player2_nickname).value

        if player1_nickname == player2_nickname:
            raise SamePlayerOnBothSidesError(
                "Both nicknames normalize to the same player"
            )

        set_score = SetScore(
            pair1_score=command.player1_score,
            pair2_score=command.player2_score,
        )
        return player1_nickname, player2_nickname, set_score
