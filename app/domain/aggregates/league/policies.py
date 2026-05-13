from __future__ import annotations

from collections.abc import Iterable

from app.domain.aggregates.league.entities import AllowlistEntry, Player, Team
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


class AllowlistPolicy:
    """Pure predicate over the league's allowlist.

    Returns the *list of missing nicknames* (normalized, de-duplicated, in
    input order of first appearance) instead of a bool, because every current
    and anticipated caller needs the diff to construct a structured error
    payload (`NotInAllowlistError(missing_nicknames=...)`).

    The "should I check at all?" gate (`LeagueRules.require_allowlist`) is
    intentionally NOT consulted here. Each call site decides whether to
    invoke the policy based on its own semantics — mirrors how
    `OneTeamPerPlayerPolicy` is gated by `LeagueRules.one_team_per_player`
    inside `League.register_players_and_team`. See
    `harness_notes/01_when_to_extract_a_policy.md`.
    """

    def find_missing_nicknames(
        self,
        candidates: Iterable[PlayerNickname],
        allowlist: list[AllowlistEntry],
    ) -> list[str]:
        allowed_set = {entry.nickname.value for entry in allowlist}
        missing: list[str] = []
        seen_missing: set[str] = set()
        for nick in candidates:
            value = nick.value
            if value in allowed_set or value in seen_missing:
                continue
            missing.append(value)
            seen_missing.add(value)
        return missing
