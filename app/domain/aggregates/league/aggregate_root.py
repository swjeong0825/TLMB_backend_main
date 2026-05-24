from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.policies import (
    NicknameUniquenessPolicy,
    OneTeamPerPlayerPolicy,
    RosterMembershipPolicy,
)
from app.domain.aggregates.league.value_objects import (
    HostToken,
    LeagueId,
    PlayerId,
    PlayerNickname,
    TeamId,
)
from app.domain.exceptions import (
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
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
    pending_deleted_player_ids: list[PlayerId] = field(default_factory=list)

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
            pending_deleted_player_ids=[],
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

    def add_players(self, nicknames: list[str]) -> list[Player]:
        """Atomic batch add of pre-registered players to the roster.

        Replaces the v5 `add_allowlist_entries`: the `allowlist_entries` side
        table no longer exists, so this writes `Player` rows directly. Each
        input nickname becomes a fresh `Player` on the roster, available to
        match submissions immediately. Players added this way have 0 teams
        and 0 matches until they appear on a confirmed match (`Team` creation
        still only happens inside `register_players_and_team`).

        Raises `NicknameAlreadyInUseError` if any input nickname (after
        `PlayerNickname` normalization) duplicates an existing roster
        nickname or another nickname inside the same batch. On error, no
        rows are added.
        """
        if not nicknames:
            raise ValueError("nicknames must be a non-empty list")

        normalized: list[PlayerNickname] = []
        seen_in_batch: set[str] = set()
        for raw in nicknames:
            nick = PlayerNickname(raw)
            if nick.value in seen_in_batch:
                raise NicknameAlreadyInUseError(
                    f"Nickname '{raw}' is duplicated within the same add request"
                )
            seen_in_batch.add(nick.value)
            normalized.append(nick)

        for nick in normalized:
            if self._find_player_by_nickname(nick) is not None:
                raise NicknameAlreadyInUseError(
                    f"Nickname '{nick.value}' is already on the roster"
                )

        new_players = [
            Player(player_id=PlayerId.generate(), nickname=nick) for nick in normalized
        ]
        self.players.extend(new_players)
        return new_players

    def remove_player(self, player_id: str) -> None:
        """Remove a pre-registered roster player.

        Raises `PlayerNotFoundError` if the id is not on the roster. Raises
        `PlayerHasParticipationError` (carries `teams_count` and
        `matches_count`) if the player is on any team or referenced by any
        match — only zero-participation players can be removed so that the
        match-history history is never silently mutated. Removed player ids
        are appended to `pending_deleted_player_ids` so the repository can
        DELETE the row on save.

        `match_count` is read from the `Player` entity (populated by the
        repository at load time); `teams_count` is derived in-aggregate from
        `self.teams`.
        """
        pid = PlayerId.from_str(player_id)
        player = self._find_player_by_id(pid)
        if player is None:
            raise PlayerNotFoundError(f"Player '{player_id}' not found in this league")

        teams_count = sum(
            1
            for t in self.teams
            if t.player_id_1 == pid or t.player_id_2 == pid
        )
        matches_count = player.match_count

        if teams_count > 0 or matches_count > 0:
            raise PlayerHasParticipationError(
                (
                    f"Player '{player_id}' has {teams_count} team(s) and "
                    f"{matches_count} match(es); only players with zero "
                    f"participation can be removed"
                ),
                player_id=player_id,
                teams_count=teams_count,
                matches_count=matches_count,
            )

        self.players = [p for p in self.players if p.player_id != pid]
        self.pending_deleted_player_ids.append(pid)

    def validate_match_participants_on_roster(self, nicknames: Iterable[str]) -> None:
        """Cross-check the four match-submission nicknames against the roster.

        No-op when `rules.auto_register_players_on_match` is True — the
        match submission path will implicitly create new `Player` rows for
        any unknown nicknames via `register_players_and_team`. When False,
        delegates to `RosterMembershipPolicy` to compute the set of missing
        nicknames; raises `RosterMembershipRequiredError` if any are
        missing. The rule-flag gate lives here (not inside the policy) so
        future call sites — e.g. `edit_player_nickname` — can decide
        independently whether and how to consult the same policy.
        """
        if self.rules.auto_register_players_on_match:
            return

        candidates = [PlayerNickname(raw) for raw in nicknames]
        missing = RosterMembershipPolicy().find_missing_nicknames(
            candidates, self.players
        )

        if missing:
            raise RosterMembershipRequiredError(
                "Match submission contains nicknames not on the roster: "
                + ", ".join(missing),
                missing_nicknames=missing,
            )

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
