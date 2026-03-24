from __future__ import annotations

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.value_objects import PlayerId, PlayerNickname, TeamId


class NicknameUniquenessPolicy:
    def is_nickname_available(
        self,
        proposed: PlayerNickname,
        players: list[Player],
        exclude_player_id: PlayerId | None = None,
    ) -> bool:
        for player in players:
            if player.nickname == proposed:
                if exclude_player_id is None or player.player_id != exclude_player_id:
                    return False
        return True


class OneTeamPerPlayerPolicy:
    def can_join_team(
        self,
        player_id: PlayerId,
        teams: list[Team],
        exclude_team_id: TeamId | None = None,
    ) -> bool:
        for team in teams:
            if exclude_team_id is not None and team.team_id == exclude_team_id:
                continue
            if team.player_id_1 == player_id or team.player_id_2 == player_id:
                return False
        return True
