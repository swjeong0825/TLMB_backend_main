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

    v5 (current) renames the v4 `require_eligible_players` key to
    `require_allowlist` (terminology unification — the feature was previously
    called "eligible players" everywhere). The behavior is identical: when
    `require_allowlist=True`, `SubmitMatchResultUseCase` rejects matches whose
    nicknames are not in the league's allowlist. See
    `Design_Doc/TLMB_Design_doc/20_allowlist.md`.

    v4 introduced the same flag under the legacy name `require_eligible_players`.
    v3 introduced `one_team_per_player = false` legality and the
    `(ranking_subject = "player", one_team_per_player = true)` cross-rule
    rejection. See `Design_Doc/TLMB_Design_doc/18_configurable_ranking_v3.md`.

    v1, v2, v3, and v4 inputs are accepted on read and upgraded transparently
    to v5 — v1 inputs additionally have the v2 ranking defaults injected
    before the v3 + v4 + v5 upgrades. v4 inputs may carry either
    `require_eligible_players` (legacy key, preferred when present) or
    `require_allowlist`; both default to `false` when omitted.
    """

    version: int
    match_pair_idempotency: MatchPairIdempotency
    one_team_per_player: bool
    ranking_subject: RankingSubject
    tie_breakers: tuple[RankingMetric, ...]
    require_allowlist: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "match_pair_idempotency": self.match_pair_idempotency,
            "one_team_per_player": self.one_team_per_player,
            "ranking_subject": self.ranking_subject,
            "tie_breakers": list(self.tie_breakers),
            "require_allowlist": self.require_allowlist,
        }

    @classmethod
    def from_dict(cls, data: Any) -> LeagueRules:
        if not isinstance(data, dict):
            raise InvalidLeagueRulesError("League rules must be a JSON object")

        version = data.get("version")
        if version not in (1, 2, 3, 4, 5):
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

        require_allowlist = cls._parse_require_allowlist(data)

        return cls(
            version=5,
            match_pair_idempotency=mpi,
            one_team_per_player=otpp,
            ranking_subject=ranking_subject,
            tie_breakers=tie_breakers,
            require_allowlist=require_allowlist,
        )

    @staticmethod
    def _parse_require_allowlist(data: dict[str, Any]) -> bool:
        # Defaults False when missing so v1/v2/v3 inputs upgrade cleanly to v5
        # without requiring callers to know about the new field. v4 inputs may
        # use the legacy key `require_eligible_players` (preferred when
        # present) or the new key `require_allowlist`; both are accepted so
        # the parser is forward- and backward-compatible.
        if "require_eligible_players" in data and data.get("require_eligible_players") is not None:
            value = data.get("require_eligible_players")
        else:
            value = data.get("require_allowlist")
        if value is None:
            return False
        if not isinstance(value, bool):
            raise InvalidLeagueRulesError(
                "require_allowlist must be a boolean"
            )
        return value

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
        ranking_subject=\"team\" / tie_breakers=[\"matches_won\"] via Alembic 003,
        version=3 (with `(player, OTPP=true)` rewritten to `(team, OTPP=true)`) via
        Alembic 004, require_eligible_players=false / version=4 via Alembic 005,
        and require_allowlist=false / version=5 (key rename of v4's
        `require_eligible_players`) via Alembic 006 — which together reproduce
        v1/v2/v3/v4 behavior byte-for-byte for every legal combo carried over
        from v3.
        """
        return cls(
            version=5,
            match_pair_idempotency="once_per_league",
            one_team_per_player=True,
            ranking_subject="team",
            tie_breakers=("matches_won",),
            require_allowlist=False,
        )
