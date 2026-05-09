from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases.get_standings_use_case import StandingsView
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError
from app.domain.services.standings_calculator import StandingsCalculator


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

    async def execute(self, query: GetStandingsByPlayerQuery) -> StandingsView:
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

        matches = await self._match_repo.get_all_by_league(league_id)
        all_entries = self._calculator.compute(
            matches, league.teams, league.players, league.rules
        )

        if league.rules.ranking_subject == "player":
            pid = str(player.player_id.value)
            filtered = [e for e in all_entries if e.player_id == pid]
            return StandingsView(entries=filtered, tie_breakers=league.rules.tie_breakers)

        # Subject = "team": surface every team the player belongs to.
        # Under OTPP=true the player has at most one team, so the result is a
        # single-element array (or empty if all of their teams have been
        # deleted). Under OTPP=false a player may belong to multiple teams and
        # all of their team rows are returned. See design doc 18.
        player_team_ids = {
            str(t.team_id.value)
            for t in league.teams
            if t.player_id_1 == player.player_id or t.player_id_2 == player.player_id
        }
        if not player_team_ids:
            return StandingsView(entries=[], tie_breakers=league.rules.tie_breakers)

        filtered = [e for e in all_entries if e.team_id in player_team_ids]
        return StandingsView(entries=filtered, tie_breakers=league.rules.tie_breakers)
