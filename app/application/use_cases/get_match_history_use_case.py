from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.aggregates.league.entities import Player, Pair
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PairId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.exceptions import LeagueNotFoundError


@dataclass
class GetMatchHistoryQuery:
    league_id: str


@dataclass
class MatchHistoryRecord:
    match_id: str
    pair1_player1_nickname: str
    pair1_player2_nickname: str
    pair2_player1_nickname: str
    pair2_player2_nickname: str
    pair1_score: str
    pair2_score: str
    created_at: datetime | None


class GetMatchHistoryUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo

    async def execute(self, query: GetMatchHistoryQuery) -> list[MatchHistoryRecord]:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        matches = await self._match_repo.get_all_by_league(league_id)

        player_map: dict[PlayerId, str] = {p.player_id: p.nickname.value for p in league.players}
        pair_map: dict[PairId, Pair] = {t.pair_id: t for t in league.pairs}

        records: list[MatchHistoryRecord] = []
        for match in matches:
            pair1 = pair_map.get(match.pair1_id)
            pair2 = pair_map.get(match.pair2_id)

            t1_p1 = player_map.get(pair1.player_id_1, "unknown") if pair1 else "unknown"
            t1_p2 = player_map.get(pair1.player_id_2, "unknown") if pair1 else "unknown"
            t2_p1 = player_map.get(pair2.player_id_1, "unknown") if pair2 else "unknown"
            t2_p2 = player_map.get(pair2.player_id_2, "unknown") if pair2 else "unknown"

            records.append(
                MatchHistoryRecord(
                    match_id=str(match.match_id.value),
                    pair1_player1_nickname=t1_p1,
                    pair1_player2_nickname=t1_p2,
                    pair2_player1_nickname=t2_p1,
                    pair2_player2_nickname=t2_p2,
                    pair1_score=match.set_score.pair1_score,
                    pair2_score=match.set_score.pair2_score,
                    created_at=match.created_at,
                )
            )

        records.sort(key=lambda r: r.created_at or datetime.min, reverse=True)
        return records
