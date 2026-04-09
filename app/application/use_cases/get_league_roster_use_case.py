from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError


@dataclass
class GetLeagueRosterQuery:
    league_id: str


@dataclass
class PlayerEntry:
    player_id: str
    nickname: str


@dataclass
class TeamEntry:
    team_id: str
    player1_nickname: str
    player2_nickname: str


@dataclass
class RosterView:
    title: str
    players: list[PlayerEntry]
    teams: list[TeamEntry]


class GetLeagueRosterUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: GetLeagueRosterQuery) -> RosterView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        player_map = {p.player_id: p.nickname.value for p in league.players}

        players = sorted(
            [PlayerEntry(player_id=str(p.player_id.value), nickname=p.nickname.value) for p in league.players],
            key=lambda e: e.nickname,
        )

        teams = sorted(
            [
                TeamEntry(
                    team_id=str(t.team_id.value),
                    player1_nickname=player_map.get(t.player_id_1, "unknown"),
                    player2_nickname=player_map.get(t.player_id_2, "unknown"),
                )
                for t in league.teams
            ],
            key=lambda e: e.player1_nickname,
        )

        return RosterView(title=league.title, players=players, teams=teams)
