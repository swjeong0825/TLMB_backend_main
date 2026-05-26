from __future__ import annotations

from dataclasses import dataclass

from app.domain.aggregates.league.value_objects import (
    PlayerId,
    PlayerNickname,
    TeamId,
)


@dataclass(init=False)
class Player:
    """Roster player.

    `rating` is optional host-curated metadata. It stays `None` for players
    auto-created by match submission until an admin sets it.

    `match_count` is a transient field populated by the repository at load
    time so that `League.remove_player` can enforce the "no participation"
    guard without re-querying. It defaults to `0` for freshly-created
    in-memory players (which by definition have no matches yet). It is
    never persisted back to the players table — it is a read-side projection
    of how many `matches` reference any team this player is on.
    """

    player_id: PlayerId
    nicknames: list[PlayerNickname]
    rating: float | None = None
    match_count: int = 0

    def __init__(
        self,
        player_id: PlayerId,
        nicknames: list[PlayerNickname] | None = None,
        rating: float | None = None,
        match_count: int = 0,
        nickname: PlayerNickname | None = None,
    ) -> None:
        if nicknames is None:
            if nickname is None:
                raise ValueError("Player must have at least one nickname")
            nicknames = [nickname]
        if not nicknames:
            raise ValueError("Player must have at least one nickname")
        self.player_id = player_id
        self.nicknames = list(nicknames)
        self.rating = rating
        self.match_count = match_count

    @property
    def canonical_nickname(self) -> PlayerNickname:
        return self.nicknames[0]

    @property
    def aliases(self) -> list[PlayerNickname]:
        return self.nicknames[1:]

    @property
    def nickname(self) -> PlayerNickname:
        """Backward-compatible alias for the canonical nickname."""
        return self.canonical_nickname

    @nickname.setter
    def nickname(self, value: PlayerNickname) -> None:
        self.nicknames[0] = value

    def has_nickname(self, candidate: PlayerNickname) -> bool:
        return any(nick == candidate for nick in self.nicknames)


@dataclass(frozen=True)
class Team:
    team_id: TeamId
    player_id_1: PlayerId
    player_id_2: PlayerId
