from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

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
    aliases: list[str] = field(default_factory=list)
    rating: float | None = None
    pairs_count: int = 0
    matches_count: int = 0


@dataclass
class PairEntry:
    pair_id: str
    player1_nickname: str
    player2_nickname: str


@dataclass
class RosterView:
    """Read model returned by `GET /leagues/{id}/roster`.

    `rules` is the serialized `LeagueRules.to_dict()` payload. The timezone
    is separate league metadata because it controls calendar boundaries for
    rules but is not itself a rule toggle.
    """

    title: str
    league_timezone: str
    rules: dict[str, Any]
    players: list[PlayerEntry]
    pairs: list[PairEntry]
    latest_match_date: date | None = None


class GetLeagueRosterUseCase:
    def __init__(self, league_repo: LeagueRepository) -> None:
        self._league_repo = league_repo

    async def execute(self, query: GetLeagueRosterQuery) -> RosterView:
        league_id = LeagueId.from_str(query.league_id)

        league = await self._league_repo.get_by_id(league_id)
        if league is None:
            raise LeagueNotFoundError(f"League '{query.league_id}' not found")

        player_map = {p.player_id: p.canonical_nickname.value for p in league.players}

        players = sorted(
            [
                PlayerEntry(
                    player_id=str(p.player_id.value),
                    nickname=p.canonical_nickname.value,
                    aliases=[alias.value for alias in p.aliases],
                    rating=p.rating,
                    pairs_count=sum(
                        1
                        for t in league.pairs
                        if t.player_id_1 == p.player_id or t.player_id_2 == p.player_id
                    ),
                    matches_count=p.match_count,
                )
                for p in league.players
            ],
            key=lambda e: e.nickname,
        )

        pairs = sorted(
            [
                PairEntry(
                    pair_id=str(t.pair_id.value),
                    player1_nickname=player_map.get(t.player_id_1, "unknown"),
                    player2_nickname=player_map.get(t.player_id_2, "unknown"),
                )
                for t in league.pairs
            ],
            key=lambda e: e.player1_nickname,
        )

        return RosterView(
            title=league.title,
            league_timezone=league.league_timezone.value,
            latest_match_date=league.latest_match_date,
            rules=league.rules.to_dict(),
            players=players,
            pairs=pairs,
        )
