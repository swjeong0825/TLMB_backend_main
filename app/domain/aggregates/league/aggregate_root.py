from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.policies import NicknameUniquenessPolicy, OneTeamPerPlayerPolicy
from app.domain.aggregates.league.value_objects import (
    HostToken,
    LeagueId,
    PlayerId,
    PlayerNickname,
    TeamId,
)
from app.domain.exceptions import (
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
    TeamNotFoundError,
)


@dataclass
class League:
    league_id: LeagueId
    host_token: HostToken
    title: str
    description: str | None
    rules: LeagueRules
    players: list[Player]
    teams: list[Team]
    pending_deleted_team_ids: list[TeamId] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        title: str,
        description: str | None,
        host_token: str,
        rules: LeagueRules | None = None,
    ) -> League:
        if not title or not title.strip():
            raise ValueError("League title cannot be blank")
        resolved_rules = rules if rules is not None else LeagueRules.default_for_new_league()
        return cls(
            league_id=LeagueId.generate(),
            host_token=HostToken(value=host_token),
            title=title,
            description=description,
            rules=resolved_rules,
            players=[],
            teams=[],
            pending_deleted_team_ids=[],
        )

    def register_players_and_team(
        self, p1_nickname: str, p2_nickname: str
    ) -> tuple[list[Player], Team]:
        nick1 = PlayerNickname(p1_nickname)
        nick2 = PlayerNickname(p2_nickname)

        if nick1 == nick2:
            raise SamePlayerWithinSingleTeamError(
                "Both nicknames normalize to the same value"
            )

        team_policy = OneTeamPerPlayerPolicy()
        enforce_one_team = self.rules.one_team_per_player

        p1 = self._find_player_by_nickname(nick1)
        p2 = self._find_player_by_nickname(nick2)

        new_players: list[Player] = []

        if p1 is None:
            p1 = Player(player_id=PlayerId.generate(), nickname=nick1)
            self.players.append(p1)
            new_players.append(p1)

        if p2 is None:
            p2 = Player(player_id=PlayerId.generate(), nickname=nick2)
            self.players.append(p2)
            new_players.append(p2)

        existing_team = self._find_team_for_players(p1.player_id, p2.player_id)
        if existing_team is not None:
            return new_players, existing_team

        if enforce_one_team:
            if not team_policy.can_join_team(p1.player_id, self.teams):
                raise TeamConflictError(
                    f"Player '{nick1.value}' is already a member of a different team"
                )
            if not team_policy.can_join_team(p2.player_id, self.teams):
                raise TeamConflictError(
                    f"Player '{nick2.value}' is already a member of a different team"
                )

        if nick1.value <= nick2.value:
            pid1, pid2 = p1.player_id, p2.player_id
        else:
            pid1, pid2 = p2.player_id, p1.player_id

        new_team = Team(team_id=TeamId.generate(), player_id_1=pid1, player_id_2=pid2)
        self.teams.append(new_team)

        return new_players, new_team

    def edit_player_nickname(self, player_id: str, new_nickname: str) -> Player:
        pid = PlayerId.from_str(player_id)
        player = self._find_player_by_id(pid)
        if player is None:
            raise PlayerNotFoundError(f"Player '{player_id}' not found in this league")

        new_nick = PlayerNickname(new_nickname)
        policy = NicknameUniquenessPolicy()
        if not policy.is_nickname_available(new_nick, self.players, exclude_player_id=pid):
            raise NicknameAlreadyInUseError(
                f"Nickname '{new_nickname}' is already in use by another player"
            )

        player.nickname = new_nick
        return player

    def delete_team(self, team_id: str) -> None:
        tid = TeamId.from_str(team_id)
        team = self._find_team_by_id(tid)
        if team is None:
            raise TeamNotFoundError(f"Team '{team_id}' not found in this league")

        self.teams = [t for t in self.teams if t.team_id != tid]
        self.pending_deleted_team_ids.append(tid)

    def _find_player_by_nickname(self, nickname: PlayerNickname) -> Player | None:
        for p in self.players:
            if p.nickname == nickname:
                return p
        return None

    def _find_player_by_id(self, player_id: PlayerId) -> Player | None:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

    def _find_team_by_id(self, team_id: TeamId) -> Team | None:
        for t in self.teams:
            if t.team_id == team_id:
                return t
        return None

    def _find_team_for_players(self, pid1: PlayerId, pid2: PlayerId) -> Team | None:
        for t in self.teams:
            if (t.player_id_1 == pid1 and t.player_id_2 == pid2) or (
                t.player_id_1 == pid2 and t.player_id_2 == pid1
            ):
                return t
        return None
