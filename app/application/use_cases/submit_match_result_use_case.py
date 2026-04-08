from __future__ import annotations

from dataclasses import dataclass

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

        team1_set = {t1_n1, t1_n2}
        team2_set = {t2_n1, t2_n2}
        if team1_set & team2_set:
            raise SamePlayerOnBothTeamsError(
                "The same player appears on both teams"
            )

        set_score = SetScore(team1_score=command.team1_score, team2_score=command.team2_score)

        async with self._uow_factory() as uow:
            league_id = LeagueId.from_str(command.league_id)
            league = await uow.league_repo.get_by_id_with_lock(league_id)
            if league is None:
                raise LeagueNotFoundError(f"League '{command.league_id}' not found")

            _, team1 = league.register_players_and_team(t1_n1, t1_n2)
            _, team2 = league.register_players_and_team(t2_n1, t2_n2)

            if league.rules.match_pair_idempotency == "once_per_league":
                pair_exists = await uow.match_repo.exists_match_for_team_pair(
                    league_id, team1.team_id, team2.team_id
                )
                if pair_exists:
                    raise DuplicateTeamPairMatchError(
                        "A match between these two teams already exists in this league"
                    )

            match = Match.create(league_id, team1.team_id, team2.team_id, set_score)

            await uow.league_repo.save(league)
            await uow.match_repo.save(match)
            await uow.commit()

        return SubmitMatchResultResult(match_id=str(match.match_id.value))
