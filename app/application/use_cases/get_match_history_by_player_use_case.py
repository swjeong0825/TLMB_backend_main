from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.domain.aggregates.league.entities import Team
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname, TeamId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError, PlayerNotFoundError


@dataclass
class GetMatchHistoryByPlayerQuery:
    league_id: str
    player_name: str


class GetMatchHistoryByPlayerUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, query: GetMatchHistoryByPlayerQuery) -> list[MatchHistoryRecord]:
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

        all_matches = await self._match_repo.get_all_by_league(league_id)
        player_matches = [
            m for m in all_matches
            if m.team1_id == team.team_id or m.team2_id == team.team_id
        ]

        player_map = {p.player_id: p.nickname.value for p in league.players}
        team_map: dict[TeamId, Team] = {t.team_id: t for t in league.teams}

        records: list[MatchHistoryRecord] = []
        for match in player_matches:
            t1 = team_map.get(match.team1_id)
            t2 = team_map.get(match.team2_id)

            t1_p1 = player_map.get(t1.player_id_1, "unknown") if t1 else "unknown"
            t1_p2 = player_map.get(t1.player_id_2, "unknown") if t1 else "unknown"
            t2_p1 = player_map.get(t2.player_id_1, "unknown") if t2 else "unknown"
            t2_p2 = player_map.get(t2.player_id_2, "unknown") if t2 else "unknown"

            records.append(
                MatchHistoryRecord(
                    match_id=str(match.match_id.value),
                    team1_player1_nickname=t1_p1,
                    team1_player2_nickname=t1_p2,
                    team2_player1_nickname=t2_p1,
                    team2_player2_nickname=t2_p2,
                    team1_score=match.set_score.team1_score,
                    team2_score=match.set_score.team2_score,
                    created_at=match.created_at,
                )
            )

        records.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
        return records
