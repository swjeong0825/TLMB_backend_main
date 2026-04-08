from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.domain.exceptions import InvalidLeagueRulesError

MatchPairIdempotency = Literal["none", "once_per_league"]


@dataclass(frozen=True)
class LeagueRules:
    """Versioned per-league configuration stored as JSONB on the league row."""

    version: int
    match_pair_idempotency: MatchPairIdempotency
    one_team_per_player: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "match_pair_idempotency": self.match_pair_idempotency,
            "one_team_per_player": self.one_team_per_player,
        }

    @classmethod
    def from_dict(cls, data: Any) -> LeagueRules:
        if not isinstance(data, dict):
            raise InvalidLeagueRulesError("League rules must be a JSON object")

        version = data.get("version")
        if version != 1:
            raise InvalidLeagueRulesError(f"Unsupported league rules version: {version!r}")

        mpi = data.get("match_pair_idempotency")
        if mpi not in ("none", "once_per_league"):
            raise InvalidLeagueRulesError(
                f"Invalid match_pair_idempotency: {mpi!r}; expected 'none' or 'once_per_league'"
            )

        otpp = data.get("one_team_per_player")
        if not isinstance(otpp, bool):
            raise InvalidLeagueRulesError("one_team_per_player must be a boolean")

        return cls(
            version=1,
            match_pair_idempotency=mpi,
            one_team_per_player=otpp,
        )

    @classmethod
    def default_for_new_league(cls) -> LeagueRules:
        """Product default when POST /leagues omits `rules` (new leagues only).

        Migrated existing DB rows use match_pair_idempotency \"none\" via Alembic backfill.
        """
        return cls(
            version=1,
            match_pair_idempotency="once_per_league",
            one_team_per_player=True,
        )
