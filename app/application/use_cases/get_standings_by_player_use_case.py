from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator, StandingsEntry


@dataclass
class GetStandingsByPlayerQuery:
    league_id: str
    player_name: str


class GetStandingsByPlayerUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._calculator = StandingsCalculator()

    async def execute(self, query: GetStandingsByPlayerQuery) -> list[StandingsEntry]:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        normalized_name = PlayerNickname(query.player_name)
        player = next(
            (p for p in league.players if p.nickname == normalized_name),
            None,
        )
        if player is None:
            raise PlayerNotFoundError(
                f"Player '{query.player_name}' not found in league '{query.league_id}'"
            )

        team = next(
            (
                t for t in league.teams
                if t.player_id_1 == player.player_id or t.player_id_2 == player.player_id
            ),
            None,
        )
        if team is None:
            return []

        matches = await self._match_repo.get_all_by_league(league_id)
        all_entries = self._calculator.compute(matches, league.teams, league.players)
        tid = str(team.team_id.value)
        return [e for e in all_entries if e.team_id == tid]
