from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.domain.aggregates.league.entities import Player, Pair
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
    - "pair": pair_id, player1_nickname, player2_nickname are populated.
    - "player": player_id, nickname are populated.

    Metric fields (matches_played, wins, losses, draws, games_won, games_lost,
    games_diff, win_pct) and `rank` are populated for both variants. `draws`
    counts matches that ended in an equal set score; it is informational only
    and does not participate in any ranking metric today.
    """

    subject_kind: Literal["pair", "player"]
    rank: int
    matches_played: int
    wins: int
    losses: int
    games_won: int
    games_lost: int
    games_diff: int
    win_pct: float
    draws: int = 0
    pair_id: str | None = None
    player1_nickname: str | None = None
    player2_nickname: str | None = None
    player_id: str | None = None
    nickname: str | None = None


@dataclass(frozen=True)
class _Aggregate:
    matches_played: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    games_won: int = 0
    games_lost: int = 0

    def add(
        self,
        won: bool,
        lost: bool,
        drew: bool,
        my_score: int,
        opp_score: int,
    ) -> _Aggregate:
        return _Aggregate(
            matches_played=self.matches_played + 1,
            wins=self.wins + (1 if won else 0),
            losses=self.losses + (1 if lost else 0),
            draws=self.draws + (1 if drew else 0),
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
        pairs: list[Pair],
        players: list[Player],
        rules: LeagueRules,
        subject: RankingSubject | None = None,
    ) -> list[StandingsEntry]:
        effective_subject: RankingSubject = subject or rules.ranking_subject
        if effective_subject == "pair":
            return self._compute_for_pairs(matches, pairs, players, rules)
        # Player-subject branch. As a configured league rule, player ranking
        # requires OTPP=false. As a read-only projection override, callers may
        # request player rows for any league; fixed pairmates simply share the
        # same metric tuple.
        return self._compute_for_players(matches, pairs, players, rules)

    def _compute_for_pairs(
        self,
        matches: list[Match],
        pairs: list[Pair],
        players: list[Player],
        rules: LeagueRules,
    ) -> list[StandingsEntry]:
        player_map = {p.player_id: p.nickname.value for p in players}

        agg_by_pair: dict[str, _Aggregate] = {
            str(pair.pair_id.value): _Aggregate() for pair in pairs
        }

        for match in matches:
            pair1_key = str(match.pair1_id.value)
            pair2_key = str(match.pair2_id.value)
            pair1_score = int(match.set_score.pair1_score)
            pair2_score = int(match.set_score.pair2_score)
            side = match.set_score.winner_side()
            if pair1_key in agg_by_pair:
                agg_by_pair[pair1_key] = agg_by_pair[pair1_key].add(
                    won=(side == "pair1"),
                    lost=(side == "pair2"),
                    drew=(side == "draw"),
                    my_score=pair1_score,
                    opp_score=pair2_score,
                )
            if pair2_key in agg_by_pair:
                agg_by_pair[pair2_key] = agg_by_pair[pair2_key].add(
                    won=(side == "pair2"),
                    lost=(side == "pair1"),
                    drew=(side == "draw"),
                    my_score=pair2_score,
                    opp_score=pair1_score,
                )

        rows: list[tuple[Pair, _Aggregate]] = [
            (pair, agg_by_pair[str(pair.pair_id.value)]) for pair in pairs
        ]
        rows = self._sort_by_tie_breakers(rows, rules.tie_breakers)

        return self._assign_ranks_pair(rows, rules.tie_breakers, player_map)

    def _compute_for_players(
        self,
        matches: list[Match],
        pairs: list[Pair],
        players: list[Player],
        rules: LeagueRules,
    ) -> list[StandingsEntry]:
        # Build, per player, the set of pairs they belong to.
        # Under v3 this branch only runs for leagues with OTPP=false (the
        # `(player, OTPP=true)` cross-rule is rejected by LeagueRules), so a
        # player may belong to multiple pairs; the aggregation naturally unions
        # match outcomes across every pair they appear on.
        pairs_for_player: dict[str, set[str]] = {}
        for pair in pairs:
            pairs_for_player.setdefault(str(pair.player_id_1.value), set()).add(
                str(pair.pair_id.value)
            )
            pairs_for_player.setdefault(str(pair.player_id_2.value), set()).add(
                str(pair.pair_id.value)
            )

        agg_by_player: dict[str, _Aggregate] = {
            str(p.player_id.value): _Aggregate() for p in players
        }

        for match in matches:
            pair1_key = str(match.pair1_id.value)
            pair2_key = str(match.pair2_id.value)
            pair1_score = int(match.set_score.pair1_score)
            pair2_score = int(match.set_score.pair2_score)
            side = match.set_score.winner_side()
            for player_id, pair_ids in pairs_for_player.items():
                if pair1_key in pair_ids and pair2_key in pair_ids:
                    # Pathological self-match — Match.create forbids it, but be safe.
                    continue
                if pair1_key in pair_ids:
                    agg_by_player[player_id] = agg_by_player[player_id].add(
                        won=(side == "pair1"),
                        lost=(side == "pair2"),
                        drew=(side == "draw"),
                        my_score=pair1_score,
                        opp_score=pair2_score,
                    )
                elif pair2_key in pair_ids:
                    agg_by_player[player_id] = agg_by_player[player_id].add(
                        won=(side == "pair2"),
                        lost=(side == "pair1"),
                        drew=(side == "draw"),
                        my_score=pair2_score,
                        opp_score=pair1_score,
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
    def _assign_ranks_pair(
        sorted_rows: list[tuple[Pair, _Aggregate]],
        tie_breakers: tuple[RankingMetric, ...],
        player_map: dict,
    ) -> list[StandingsEntry]:
        entries: list[StandingsEntry] = []
        prev_key: tuple | None = None
        prev_rank = 0
        for position, (pair, agg) in enumerate(sorted_rows, start=1):
            current_key = tuple(agg.metric_value(m) for m in tie_breakers)
            if prev_key is not None and current_key == prev_key:
                rank = prev_rank
            else:
                rank = position
                prev_rank = rank
                prev_key = current_key

            pair_id_str = str(pair.pair_id.value)
            nick1 = player_map.get(pair.player_id_1, "unknown")
            nick2 = player_map.get(pair.player_id_2, "unknown")

            entries.append(
                StandingsEntry(
                    subject_kind="pair",
                    rank=rank,
                    matches_played=agg.matches_played,
                    wins=agg.wins,
                    losses=agg.losses,
                    games_won=agg.games_won,
                    games_lost=agg.games_lost,
                    games_diff=agg.games_diff,
                    win_pct=agg.win_pct,
                    draws=agg.draws,
                    pair_id=pair_id_str,
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
                    draws=agg.draws,
                    player_id=str(player.player_id.value),
                    nickname=player.nickname.value,
                )
            )
        return entries
