from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.aggregates.league.entities import Player, Pair
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PairId
from app.domain.aggregates.match.repository import MatchRepository
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository
from app.domain.exceptions import LeagueNotFoundError

MatchScope = Literal["doubles", "singles", "both"]


@dataclass
class GetMatchHistoryQuery:
    league_id: str
    scope: MatchScope = "doubles"


@dataclass
class MatchHistoryRecord:
    match_id: str
    match_format: Literal["doubles", "singles"] = "doubles"
    created_at: datetime | None = None
    pair1_player1_nickname: str | None = None
    pair1_player2_nickname: str | None = None
    pair2_player1_nickname: str | None = None
    pair2_player2_nickname: str | None = None
    pair1_score: str | None = None
    pair2_score: str | None = None
    player1_nickname: str | None = None
    player2_nickname: str | None = None
    player1_score: str | None = None
    player2_score: str | None = None


class GetMatchHistoryUseCase:
    def __init__(
        self,
        league_repo: LeagueRepository,
        match_repo: MatchRepository,
        singles_match_repo: SinglesMatchRepository | None = None,
    ) -> None:
        self._league_repo = league_repo
        self._match_repo = match_repo
        self._singles_match_repo = singles_match_repo

    async def execute(self, query: GetMatchHistoryQuery) -> list[MatchHistoryRecord]:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        player_map: dict[PlayerId, str] = {p.player_id: p.nickname.value for p in league.players}
        pair_map: dict[PairId, Pair] = {t.pair_id: t for t in league.pairs}

        records: list[MatchHistoryRecord] = []
        if query.scope in ("doubles", "both"):
            matches = await self._match_repo.get_all_by_league(league_id)
            records.extend(self._doubles_records(matches, player_map, pair_map))
        if query.scope in ("singles", "both") and self._singles_match_repo is not None:
            singles_matches = await self._singles_match_repo.get_all_by_league(league_id)
            records.extend(self._singles_records(singles_matches, player_map))

        records.sort(key=_created_sort_key, reverse=True)
        return records

    @staticmethod
    def _doubles_records(matches, player_map, pair_map) -> list[MatchHistoryRecord]:
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
                    match_format="doubles",
                    created_at=match.created_at,
                    pair1_player1_nickname=t1_p1,
                    pair1_player2_nickname=t1_p2,
                    pair2_player1_nickname=t2_p1,
                    pair2_player2_nickname=t2_p2,
                    pair1_score=match.set_score.pair1_score,
                    pair2_score=match.set_score.pair2_score,
                )
            )
        return records

    @staticmethod
    def _singles_records(singles_matches, player_map) -> list[MatchHistoryRecord]:
        records: list[MatchHistoryRecord] = []
        for match in singles_matches:
            records.append(
                MatchHistoryRecord(
                    match_id=str(match.match_id.value),
                    match_format="singles",
                    created_at=match.created_at,
                    player1_nickname=player_map.get(match.player1_id, "unknown"),
                    player2_nickname=player_map.get(match.player2_id, "unknown"),
                    player1_score=match.set_score.pair1_score,
                    player2_score=match.set_score.pair2_score,
                )
            )
        return records


def _created_sort_key(record: MatchHistoryRecord) -> float:
    if record.created_at is None:
        return 0.0
    return record.created_at.timestamp()
