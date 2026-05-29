from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueCreated:
    league_id: str
    title: str


@dataclass(frozen=True)
class PlayersAndPairRegistered:
    league_id: str
    new_player_ids: tuple[str, ...]
    pair_id: str


@dataclass(frozen=True)
class PlayerNicknameEdited:
    league_id: str
    player_id: str
    old_nickname: str
    new_nickname: str


@dataclass(frozen=True)
class PairDeleted:
    league_id: str
    pair_id: str
