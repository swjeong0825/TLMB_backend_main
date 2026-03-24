from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueCreated:
    league_id: str
    title: str


@dataclass(frozen=True)
class PlayersAndTeamRegistered:
    league_id: str
    new_player_ids: tuple[str, ...]
    team_id: str


@dataclass(frozen=True)
class PlayerNicknameEdited:
    league_id: str
    player_id: str
    old_nickname: str
    new_nickname: str


@dataclass(frozen=True)
class TeamDeleted:
    league_id: str
    team_id: str
