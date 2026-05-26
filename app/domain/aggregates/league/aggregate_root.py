from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo

from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.league_rules import LeagueRules
from app.domain.aggregates.league.policies import (
    NicknameUniquenessPolicy,
    OneTeamPerPlayerPolicy,
    RosterMembershipPolicy,
)
from app.domain.aggregates.league.value_objects import (
    DEFAULT_LEAGUE_TIMEZONE,
    HostEmail,
    HostToken,
    LeagueId,
    LeagueTimezone,
    PlayerId,
    PlayerNickname,
    TeamId,
)
from app.domain.exceptions import (
    CannotRemoveCanonicalNicknameError,
    InvalidPlayerRatingError,
    LastNicknameError,
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
    TeamConflictError,
    TeamNotFoundError,
)


@dataclass
class League:
    league_id: LeagueId
    host_token: HostToken
    host_email: HostEmail
    league_timezone: LeagueTimezone
    latest_match_date: date | None
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
        host_email: str,
        league_timezone: str = DEFAULT_LEAGUE_TIMEZONE,
        rules: LeagueRules | None = None,
    ) -> League:
        if not title or not title.strip():
            raise ValueError("League title cannot be blank")
        resolved_rules = rules if rules is not None else LeagueRules.default_for_new_league()
        return cls(
            league_id=LeagueId.generate(),
            host_token=HostToken(value=host_token),
            host_email=HostEmail(value=host_email),
            league_timezone=LeagueTimezone(value=league_timezone),
            latest_match_date=None,
            title=title,
            description=description,
            rules=resolved_rules,
            players=[],
            teams=[],
            pending_deleted_team_ids=[],
            pending_deleted_player_ids=[],
        )

    def note_match_recorded_at(self, created_at: datetime) -> None:
        """Update league metadata from a persisted match timestamp."""
        local_date = self._local_date_for(created_at)
        if self.latest_match_date is None or local_date > self.latest_match_date:
            self.latest_match_date = local_date

    def reset_latest_match_date(self, created_at: datetime | None) -> None:
        self.latest_match_date = (
            self._local_date_for(created_at) if created_at is not None else None
        )

    def _local_date_for(self, created_at: datetime) -> date:
        dt = created_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(self.league_timezone.value)).date()

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
            p1 = Player(player_id=PlayerId.generate(), nicknames=[nick1])
            self.players.append(p1)
            new_players.append(p1)

        if p2 is None:
            p2 = Player(player_id=PlayerId.generate(), nicknames=[nick2])
            self.players.append(p2)
            new_players.append(p2)

        if p1.player_id == p2.player_id:
            raise SamePlayerWithinSingleTeamError(
                "Both nicknames resolve to the same player"
            )

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
        if new_nick == player.canonical_nickname:
            return player
        if player.has_nickname(new_nick):
            player.nicknames = [
                new_nick,
                *[nick for nick in player.aliases if nick != new_nick],
            ]
            return player

        policy = NicknameUniquenessPolicy()
        if not policy.is_nickname_available(new_nick, self.players, exclude_player_id=pid):
            raise NicknameAlreadyInUseError(
                f"Nickname '{new_nickname}' is already in use by another player"
            )

        player.nicknames = [new_nick, *player.aliases]
        return player

    def add_alias_to_player(self, player_id: str, alias: str) -> Player:
        pid = PlayerId.from_str(player_id)
        player = self._find_player_by_id(pid)
        if player is None:
            raise PlayerNotFoundError(f"Player '{player_id}' not found in this league")

        alias_nick = PlayerNickname(alias)
        policy = NicknameUniquenessPolicy()
        if not policy.is_nickname_available(alias_nick, self.players):
            raise NicknameAlreadyInUseError(
                f"Nickname '{alias_nick.value}' is already in use in this league"
            )

        player.nicknames.append(alias_nick)
        return player

    def remove_alias_from_player(self, player_id: str, alias: str) -> Player:
        pid = PlayerId.from_str(player_id)
        player = self._find_player_by_id(pid)
        if player is None:
            raise PlayerNotFoundError(f"Player '{player_id}' not found in this league")

        alias_nick = PlayerNickname(alias)
        if alias_nick == player.canonical_nickname:
            raise CannotRemoveCanonicalNicknameError(
                (
                    f"Cannot remove canonical nickname "
                    f"'{player.canonical_nickname.value}' directly"
                ),
                player_id=player_id,
                canonical_nickname=player.canonical_nickname.value,
            )
        if len(player.nicknames) <= 1:
            raise LastNicknameError(
                f"Cannot remove the last nickname for player '{player_id}'",
                player_id=player_id,
            )
        if not player.has_nickname(alias_nick):
            raise PlayerNotFoundError(
                f"Alias '{alias_nick.value}' not found for player '{player_id}'"
            )

        player.nicknames = [nick for nick in player.nicknames if nick != alias_nick]
        return player

    def update_player_rating(self, player_id: str, rating: float | None) -> Player:
        pid = PlayerId.from_str(player_id)
        player = self._find_player_by_id(pid)
        if player is None:
            raise PlayerNotFoundError(f"Player '{player_id}' not found in this league")

        player.rating = self._normalize_rating(rating)
        return player

    def delete_team(self, team_id: str) -> None:
        tid = TeamId.from_str(team_id)
        team = self._find_team_by_id(tid)
        if team is None:
            raise TeamNotFoundError(f"Team '{team_id}' not found in this league")

        self.teams = [t for t in self.teams if t.team_id != tid]
        self.pending_deleted_team_ids.append(tid)

    def add_players(
        self,
        nicknames: list[str],
        ratings: list[float | None] | None = None,
    ) -> list[Player]:
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
        if ratings is not None and len(ratings) != len(nicknames):
            raise ValueError("ratings must have the same length as nicknames")

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

        normalized_ratings = (
            [None for _ in normalized]
            if ratings is None
            else [self._normalize_rating(rating) for rating in ratings]
        )
        new_players = [
            Player(player_id=PlayerId.generate(), nicknames=[nick], rating=rating)
            for nick, rating in zip(normalized, normalized_ratings)
        ]
        self.players.extend(new_players)
        return new_players

    def validate_teams_do_not_share_players(self, team1: Team, team2: Team) -> None:
        team1_player_ids = {team1.player_id_1, team1.player_id_2}
        team2_player_ids = {team2.player_id_1, team2.player_id_2}
        if team1_player_ids & team2_player_ids:
            raise SamePlayerOnBothTeamsError(
                "The same player appears on both teams"
            )

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
            if p.has_nickname(nickname):
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

    @staticmethod
    def _normalize_rating(rating: float | None) -> float | None:
        if rating is None:
            return None
        if not isfinite(rating) or rating < 0:
            raise InvalidPlayerRatingError(
                "Player rating must be a non-negative finite number"
            )
        return float(rating)
