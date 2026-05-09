from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.league_rules import (
    LeagueRules,
    RankingMetric,
    RankingSubject,
)
from app.domain.aggregates.match.aggregate_root import Match


@dataclass(frozen=True)
class StandingsEntry:
    """Discriminated row in a standings response.

    `subject_kind` selects which set of identifier/display fields applies:
    - "team": team_id, player1_nickname, player2_nickname are populated.
    - "player": player_id, nickname are populated.

    Metric fields (matches_played, wins, losses, games_won, games_lost,
    games_diff, win_pct) and `rank` are populated for both variants.
    """

    subject_kind: Literal["team", "player"]
    rank: int
    matches_played: int
    wins: int
    losses: int
    games_won: int
    games_lost: int
    games_diff: int
    win_pct: float
    team_id: str | None = None
    player1_nickname: str | None = None
    player2_nickname: str | None = None
    player_id: str | None = None
    nickname: str | None = None


@dataclass(frozen=True)
class _Aggregate:
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    games_won: int = 0
    games_lost: int = 0

    def add(
        self,
        won: bool,
        lost: bool,
        my_score: int,
        opp_score: int,
    ) -> _Aggregate:
        return _Aggregate(
            matches_played=self.matches_played + 1,
            wins=self.wins + (1 if won else 0),
            losses=self.losses + (1 if lost else 0),
            games_won=self.games_won + my_score,
            games_lost=self.games_lost + opp_score,
        )

    @property
    def games_diff(self) -> int:
        return self.games_won - self.games_lost

    @property
    def win_pct(self) -> float:
        if self.matches_played == 0:
            return 0.0
        return self.wins / self.matches_played

    def metric_value(self, metric: RankingMetric) -> int | float:
        if metric == "matches_won":
            return self.wins
        if metric == "match_diff":
            return self.wins - self.losses
        if metric == "games_won":
            return self.games_won
        if metric == "games_lost":
            # Lower is better — negate so a uniform descending sort works.
            return -self.games_lost
        if metric == "games_diff":
            return self.games_diff
        if metric == "win_pct":
            return self.win_pct
        raise ValueError(f"Unknown ranking metric: {metric!r}")


class StandingsCalculator:
    def compute(
        self,
        matches: list[Match],
        teams: list[Team],
        players: list[Player],
        rules: LeagueRules,
    ) -> list[StandingsEntry]:
        subject: RankingSubject = rules.ranking_subject
        if subject == "team":
            return self._compute_for_teams(matches, teams, players, rules)
        # Player-subject branch. Under v3 the (player, OTPP=true) cross-rule is
        # rejected by `LeagueRules.from_dict`, so this branch only ever runs for
        # leagues with one_team_per_player=false. Each player row aggregates
        # per-match outcomes across every team the player belongs to, so a
        # player who partnered with different teammates across matches can have
        # a different metric tuple than any individual teammate.
        # See design doc 18 (configurable_ranking_v3).
        return self._compute_for_players(matches, teams, players, rules)

    def _compute_for_teams(
        self,
        matches: list[Match],
        teams: list[Team],
        players: list[Player],
        rules: LeagueRules,
    ) -> list[StandingsEntry]:
        player_map = {p.player_id: p.nickname.value for p in players}

        agg_by_team: dict[str, _Aggregate] = {
            str(t.team_id.value): _Aggregate() for t in teams
        }

        for match in matches:
            t1 = str(match.team1_id.value)
            t2 = str(match.team2_id.value)
            s1 = int(match.set_score.team1_score)
            s2 = int(match.set_score.team2_score)
            side = match.set_score.winner_side()
            if t1 in agg_by_team:
                agg_by_team[t1] = agg_by_team[t1].add(
                    won=(side == "team1"),
                    lost=(side == "team2"),
                    my_score=s1,
                    opp_score=s2,
                )
            if t2 in agg_by_team:
                agg_by_team[t2] = agg_by_team[t2].add(
                    won=(side == "team2"),
                    lost=(side == "team1"),
                    my_score=s2,
                    opp_score=s1,
                )

        rows: list[tuple[Team, _Aggregate]] = [
            (t, agg_by_team[str(t.team_id.value)]) for t in teams
        ]
        rows = self._sort_by_tie_breakers(rows, rules.tie_breakers)

        return self._assign_ranks_team(rows, rules.tie_breakers, player_map)

    def _compute_for_players(
        self,
        matches: list[Match],
        teams: list[Team],
        players: list[Player],
        rules: LeagueRules,
    ) -> list[StandingsEntry]:
        # Build, per player, the set of teams they belong to.
        # Under v3 this branch only runs for leagues with OTPP=false (the
        # `(player, OTPP=true)` cross-rule is rejected by LeagueRules), so a
        # player may belong to multiple teams; the aggregation naturally unions
        # match outcomes across every team they appear on.
        teams_for_player: dict[str, set[str]] = {}
        for t in teams:
            teams_for_player.setdefault(str(t.player_id_1.value), set()).add(
                str(t.team_id.value)
            )
            teams_for_player.setdefault(str(t.player_id_2.value), set()).add(
                str(t.team_id.value)
            )

        agg_by_player: dict[str, _Aggregate] = {
            str(p.player_id.value): _Aggregate() for p in players
        }

        for match in matches:
            t1 = str(match.team1_id.value)
            t2 = str(match.team2_id.value)
            s1 = int(match.set_score.team1_score)
            s2 = int(match.set_score.team2_score)
            side = match.set_score.winner_side()
            for player_id, team_ids in teams_for_player.items():
                if t1 in team_ids and t2 in team_ids:
                    # Pathological self-match — Match.create forbids it, but be safe.
                    continue
                if t1 in team_ids:
                    agg_by_player[player_id] = agg_by_player[player_id].add(
                        won=(side == "team1"),
                        lost=(side == "team2"),
                        my_score=s1,
                        opp_score=s2,
                    )
                elif t2 in team_ids:
                    agg_by_player[player_id] = agg_by_player[player_id].add(
                        won=(side == "team2"),
                        lost=(side == "team1"),
                        my_score=s2,
                        opp_score=s1,
                    )

        rows: list[tuple[Player, _Aggregate]] = [
            (p, agg_by_player[str(p.player_id.value)]) for p in players
        ]
        rows = self._sort_by_tie_breakers(rows, rules.tie_breakers)

        return self._assign_ranks_player(rows, rules.tie_breakers)

    @staticmethod
    def _sort_by_tie_breakers(
        rows: list,
        tie_breakers: tuple[RankingMetric, ...],
    ) -> list:
        return sorted(
            rows,
            key=lambda row: tuple(row[1].metric_value(m) for m in tie_breakers),
            reverse=True,
        )

    @staticmethod
    def _assign_ranks_team(
        sorted_rows: list[tuple[Team, _Aggregate]],
        tie_breakers: tuple[RankingMetric, ...],
        player_map: dict,
    ) -> list[StandingsEntry]:
        entries: list[StandingsEntry] = []
        prev_key: tuple | None = None
        prev_rank = 0
        for position, (team, agg) in enumerate(sorted_rows, start=1):
            current_key = tuple(agg.metric_value(m) for m in tie_breakers)
            if prev_key is not None and current_key == prev_key:
                rank = prev_rank
            else:
                rank = position
                prev_rank = rank
                prev_key = current_key

            team_id_str = str(team.team_id.value)
            nick1 = player_map.get(team.player_id_1, "unknown")
            nick2 = player_map.get(team.player_id_2, "unknown")

            entries.append(
                StandingsEntry(
                    subject_kind="team",
                    rank=rank,
                    matches_played=agg.matches_played,
                    wins=agg.wins,
                    losses=agg.losses,
                    games_won=agg.games_won,
                    games_lost=agg.games_lost,
                    games_diff=agg.games_diff,
                    win_pct=agg.win_pct,
                    team_id=team_id_str,
                    player1_nickname=nick1,
                    player2_nickname=nick2,
                )
            )
        return entries

    @staticmethod
    def _assign_ranks_player(
        sorted_rows: list[tuple[Player, _Aggregate]],
        tie_breakers: tuple[RankingMetric, ...],
    ) -> list[StandingsEntry]:
        entries: list[StandingsEntry] = []
        prev_key: tuple | None = None
        prev_rank = 0
        for position, (player, agg) in enumerate(sorted_rows, start=1):
            current_key = tuple(agg.metric_value(m) for m in tie_breakers)
            if prev_key is not None and current_key == prev_key:
                rank = prev_rank
            else:
                rank = position
                prev_rank = rank
                prev_key = current_key

            entries.append(
                StandingsEntry(
                    subject_kind="player",
                    rank=rank,
                    matches_played=agg.matches_played,
                    wins=agg.wins,
                    losses=agg.losses,
                    games_won=agg.games_won,
                    games_lost=agg.games_lost,
                    games_diff=agg.games_diff,
                    win_pct=agg.win_pct,
                    player_id=str(player.player_id.value),
                    nickname=player.nickname.value,
                )
            )
        return entries
