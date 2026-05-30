from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.application.unit_of_work.submit_singles_match_result_uow import (
    SubmitSinglesMatchResultUnitOfWork,
)
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.exceptions import (
    LeagueNotFoundError,
    SamePlayerOnBothSidesError,
)


@dataclass
class SubmitSinglesMatchResultCommand:
    league_id: str
    player1_nickname: str
    player2_nickname: str
    player1_score: str
    player2_score: str


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
        player1_nickname = command.player1_nickname.lower().strip()
        player2_nickname = command.player2_nickname.lower().strip()

        if player1_nickname == player2_nickname:
            raise SamePlayerOnBothSidesError(
                "Both nicknames normalize to the same player"
            )

        set_score = SetScore(
            pair1_score=command.player1_score,
            pair2_score=command.player2_score,
        )

        async with self._uow_factory() as uow:
            league_id = LeagueId.from_str(command.league_id)
            league = await uow.league_repo.get_by_id_with_lock(league_id)
            if league is None:
                raise LeagueNotFoundError(f"League '{command.league_id}' not found")

            league.validate_match_participants_on_roster(
                [player1_nickname, player2_nickname]
            )
            player1 = league.register_single_player(player1_nickname)
            player2 = league.register_single_player(player2_nickname)
            if player1.player_id == player2.player_id:
                raise SamePlayerOnBothSidesError(
                    "Both nicknames resolve to the same player"
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
            await uow.commit()

        return SubmitSinglesMatchResultResult(
            match_id=str(match.match_id.value),
            created_at=created_at,
        )
