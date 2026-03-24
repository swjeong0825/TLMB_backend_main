from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname, TeamId


@dataclass
class Player:
    player_id: PlayerId
    nickname: PlayerNickname


@dataclass(frozen=True)
class Team:
    team_id: TeamId
    player_id_1: PlayerId
    player_id_2: PlayerId
