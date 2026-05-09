from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from app.domain.exceptions import InvalidLeagueRulesError

MatchPairIdempotency = Literal["none", "once_per_league"]
RankingSubject = Literal["team", "player"]
RankingMetric = Literal[
    "matches_won",
    "match_diff",
    "games_won",
    "games_lost",
    "games_diff",
    "win_pct",
]

ALLOWED_METRICS: tuple[RankingMetric, ...] = get_args(RankingMetric)


@dataclass(frozen=True)
class LeagueRules:
    """Versioned per-league configuration stored as JSONB on the league row.

    v3 (current) accepts `one_team_per_player = false` and enforces the
    `(ranking_subject = "player", one_team_per_player = true)` cross-rule
    rejection. v1 and v2 inputs are accepted on read and upgraded transparently
    to v3 — v1 inputs additionally have the v2 ranking defaults injected before
    the v3 upgrade. See the design docs
    `Design_Doc/TLMB_Design_doc/17_configurable_ranking.md` (v2) and
    `Design_Doc/TLMB_Design_doc/18_configurable_ranking_v3.md` (v3).
    """

    version: int
    match_pair_idempotency: MatchPairIdempotency
    one_team_per_player: bool
    ranking_subject: RankingSubject
    tie_breakers: tuple[RankingMetric, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "match_pair_idempotency": self.match_pair_idempotency,
            "one_team_per_player": self.one_team_per_player,
            "ranking_subject": self.ranking_subject,
            "tie_breakers": list(self.tie_breakers),
        }

    @classmethod
    def from_dict(cls, data: Any) -> LeagueRules:
        if not isinstance(data, dict):
            raise InvalidLeagueRulesError("League rules must be a JSON object")

        version = data.get("version")
        if version not in (1, 2, 3):
            raise InvalidLeagueRulesError(f"Unsupported league rules version: {version!r}")

        mpi = data.get("match_pair_idempotency")
        if mpi not in ("none", "once_per_league"):
            raise InvalidLeagueRulesError(
                f"Invalid match_pair_idempotency: {mpi!r}; expected 'none' or 'once_per_league'"
            )

        otpp = data.get("one_team_per_player")
        if not isinstance(otpp, bool):
            raise InvalidLeagueRulesError("one_team_per_player must be a boolean")

        if version == 1:
            ranking_subject: RankingSubject = "team"
            tie_breakers: tuple[RankingMetric, ...] = ("matches_won",)
        else:
            ranking_subject = cls._parse_ranking_subject(data.get("ranking_subject"))
            tie_breakers = cls._parse_tie_breakers(data.get("tie_breakers"))

        if ranking_subject == "player" and otpp is True:
            raise InvalidLeagueRulesError(
                "ranking_subject='player' requires one_team_per_player=false; "
                "pick (team, OTPP=true) or (player, OTPP=false)"
            )

        return cls(
            version=3,
            match_pair_idempotency=mpi,
            one_team_per_player=otpp,
            ranking_subject=ranking_subject,
            tie_breakers=tie_breakers,
        )

    @staticmethod
    def _parse_ranking_subject(value: Any) -> RankingSubject:
        if value not in ("team", "player"):
            raise InvalidLeagueRulesError(
                f"Invalid ranking_subject: {value!r}; expected 'team' or 'player'"
            )
        return value

    @staticmethod
    def _parse_tie_breakers(value: Any) -> tuple[RankingMetric, ...]:
        if not isinstance(value, list) or len(value) == 0:
            raise InvalidLeagueRulesError(
                "tie_breakers must be a non-empty list of metric names"
            )
        seen: set[str] = set()
        parsed: list[RankingMetric] = []
        for entry in value:
            if entry not in ALLOWED_METRICS:
                raise InvalidLeagueRulesError(
                    f"Invalid tie_breakers entry: {entry!r}; "
                    f"expected one of {list(ALLOWED_METRICS)}"
                )
            if entry in seen:
                raise InvalidLeagueRulesError(
                    f"Duplicate tie_breakers entry: {entry!r}"
                )
            seen.add(entry)
            parsed.append(entry)
        return tuple(parsed)

    @classmethod
    def default_for_new_league(cls) -> LeagueRules:
        """Product default when POST /leagues omits `rules` (new leagues only).

        Migrated existing DB rows use match_pair_idempotency \"none\" via Alembic 002,
        ranking_subject=\"team\" / tie_breakers=[\"matches_won\"] via Alembic 003, and
        version=3 (with `(player, OTPP=true)` rewritten to `(team, OTPP=true)`) via
        Alembic 004 — which together reproduce v1/v2 behavior byte-for-byte for
        every legal combo carried over from v2.
        """
        return cls(
            version=3,
            match_pair_idempotency="once_per_league",
            one_team_per_player=True,
            ranking_subject="team",
            tie_breakers=("matches_won",),
        )
