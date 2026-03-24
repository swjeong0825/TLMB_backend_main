from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.match.aggregate_root import Match


@dataclass
class StandingsEntry:
    team_id: str
    player1_nickname: str
    player2_nickname: str
    wins: int
    losses: int
    rank: int


class StandingsCalculator:
    def compute(
        self,
        matches: list[Match],
        teams: list[Team],
        players: list[Player],
    ) -> list[StandingsEntry]:
        player_map = {p.player_id: p.nickname.value for p in players}

        win_counts: dict[str, int] = {str(t.team_id.value): 0 for t in teams}
        loss_counts: dict[str, int] = {str(t.team_id.value): 0 for t in teams}

        for match in matches:
            t1 = str(match.team1_id.value)
            t2 = str(match.team2_id.value)
            side = match.set_score.winner_side()
            if side == "team1":
                win_counts[t1] = win_counts.get(t1, 0) + 1
                loss_counts[t2] = loss_counts.get(t2, 0) + 1
            elif side == "team2":
                win_counts[t2] = win_counts.get(t2, 0) + 1
                loss_counts[t1] = loss_counts.get(t1, 0) + 1

        sorted_teams = sorted(teams, key=lambda t: win_counts.get(str(t.team_id.value), 0), reverse=True)

        entries: list[StandingsEntry] = []
        current_rank = 1
        for position, team in enumerate(sorted_teams, start=1):
            team_id_str = str(team.team_id.value)
            wins = win_counts.get(team_id_str, 0)

            if position > 1:
                prev_wins = win_counts.get(str(sorted_teams[position - 2].team_id.value), 0)
                if wins < prev_wins:
                    current_rank = position

            nick1 = player_map.get(team.player_id_1, "unknown")
            nick2 = player_map.get(team.player_id_2, "unknown")

            entries.append(
                StandingsEntry(
                    team_id=team_id_str,
                    player1_nickname=nick1,
                    player2_nickname=nick2,
                    wins=wins,
                    losses=loss_counts.get(team_id_str, 0),
                    rank=current_rank,
                )
            )

        return entries
