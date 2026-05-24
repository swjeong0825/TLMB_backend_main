from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.value_objects import (
    PlayerId,
    PlayerNickname,
    TeamId,
)


@dataclass
class Player:
    """Roster player.

    `match_count` is a transient field populated by the repository at load
    time so that `League.remove_player` can enforce the "no participation"
    guard without re-querying. It defaults to `0` for freshly-created
    in-memory players (which by definition have no matches yet). It is
    never persisted back to the players table — it is a read-side projection
    of how many `matches` reference any team this player is on.
    """

    player_id: PlayerId
    nickname: PlayerNickname
    match_count: int = 0


@dataclass(frozen=True)
class Team:
    team_id: TeamId
    player_id_1: PlayerId
    player_id_2: PlayerId
