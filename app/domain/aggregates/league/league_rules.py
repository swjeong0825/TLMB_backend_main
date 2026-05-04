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

    v2 (current) adds `ranking_subject` and `tie_breakers` for configurable ranking.
    v1 inputs are accepted on read and upgraded transparently to v2 by injecting
    the v2 ranking defaults; see `from_dict` and the design doc
    `Design_Doc/TLMB_Design_doc/17_configurable_ranking.md`.
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
        if version not in (1, 2):
            raise InvalidLeagueRulesError(f"Unsupported league rules version: {version!r}")

        mpi = data.get("match_pair_idempotency")
        if mpi not in ("none", "once_per_league"):
            raise InvalidLeagueRulesError(
                f"Invalid match_pair_idempotency: {mpi!r}; expected 'none' or 'once_per_league'"
            )

        otpp = data.get("one_team_per_player")
        if not isinstance(otpp, bool):
            raise InvalidLeagueRulesError("one_team_per_player must be a boolean")

        # TODO(v3-ranking-tightening): v2 locks one_team_per_player to true;
        # v3 will accept false and add a (ranking_subject, OTPP) cross-rule
        # rejecting (player, OTPP=true). Loosen this check and introduce the
        # cross-rule together; see design doc 17.
        if otpp is not True:
            raise InvalidLeagueRulesError(
                "one_team_per_player must be true in v2; "
                "configurable one_team_per_player arrives in v3"
            )

        if version == 1:
            ranking_subject: RankingSubject = "team"
            tie_breakers: tuple[RankingMetric, ...] = ("matches_won",)
        else:
            ranking_subject = cls._parse_ranking_subject(data.get("ranking_subject"))
            tie_breakers = cls._parse_tie_breakers(data.get("tie_breakers"))

        return cls(
            version=2,
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
        and ranking_subject=\"team\" / tie_breakers=[\"matches_won\"] via Alembic 003,
        which together reproduce v1 behavior byte-for-byte.
        """
        return cls(
            version=2,
            match_pair_idempotency="once_per_league",
            one_team_per_player=True,
            ranking_subject="team",
            tie_breakers=("matches_won",),
        )
