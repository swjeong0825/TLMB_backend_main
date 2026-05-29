from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases.get_match_history_use_case import MatchHistoryRecord
from app.domain.aggregates.league.entities import Pair
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerNickname, PairId
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
            (p for p in league.players if p.has_nickname(normalized_name)),
            None,
        )
        if player is None:
            raise PlayerNotFoundError(
                f"Player '{query.player_name}' not found in league '{query.league_id}'"
            )

        # Under OTPP=true the player has at most one pair. Under OTPP=false
        # they may belong to multiple pairs; the repo returns the union of
        # matches across every supplied pair ID, deduped by `match_id`. See
        # design doc 18.
        pair_ids = [
            pair.pair_id
            for pair in league.pairs
            if pair.player_id_1 == player.player_id
            or pair.player_id_2 == player.player_id
        ]
        if not pair_ids:
            return []

        player_matches = await self._match_repo.get_all_by_player(league_id, pair_ids)

        player_map = {p.player_id: p.canonical_nickname.value for p in league.players}
        pair_map: dict[PairId, Pair] = {pair.pair_id: pair for pair in league.pairs}

        records: list[MatchHistoryRecord] = []
        for match in player_matches:
            pair1 = pair_map.get(match.pair1_id)
            pair2 = pair_map.get(match.pair2_id)

            pair1_player1 = (
                player_map.get(pair1.player_id_1, "unknown") if pair1 else "unknown"
            )
            pair1_player2 = (
                player_map.get(pair1.player_id_2, "unknown") if pair1 else "unknown"
            )
            pair2_player1 = (
                player_map.get(pair2.player_id_1, "unknown") if pair2 else "unknown"
            )
            pair2_player2 = (
                player_map.get(pair2.player_id_2, "unknown") if pair2 else "unknown"
            )

            records.append(
                MatchHistoryRecord(
                    match_id=str(match.match_id.value),
                    pair1_player1_nickname=pair1_player1,
                    pair1_player2_nickname=pair1_player2,
                    pair2_player1_nickname=pair2_player1,
                    pair2_player2_nickname=pair2_player2,
                    pair1_score=match.set_score.pair1_score,
                    pair2_score=match.set_score.pair2_score,
                    created_at=match.created_at,
                )
            )

        return records
