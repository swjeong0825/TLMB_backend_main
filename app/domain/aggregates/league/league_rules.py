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

    v6 (current) retires the allowlist concept entirely (the
    `allowlist_entries` side table is dropped in alembic `007`). The v5
    `require_allowlist` flag is replaced by `auto_register_players_on_match`
    with the boolean *inverted*: pre-existing leagues with
    `require_allowlist=true` (allowlist required) become
    `auto_register_players_on_match=false` (only pre-registered roster
    members can play); pre-existing leagues with `require_allowlist=false`
    become `auto_register_players_on_match=true`, which is also the new
    default for fresh leagues. The legacy "allowlist-only" behavior is
    preserved end-to-end by `League.validate_match_participants_on_roster`,
    which now checks the roster (`self.players`) directly.

    v5 renamed v4's `require_eligible_players` to `require_allowlist`; v4
    introduced the same flag under the legacy name `require_eligible_players`;
    v3 introduced `one_team_per_player = false` legality. v1..v5 inputs are
    accepted on read and upgraded transparently to v6 (the boolean flip
    happens during parse). v4 inputs may carry either `require_eligible_players`
    or `require_allowlist`; v5 inputs carry `require_allowlist`; v6 inputs
    carry `auto_register_players_on_match`.
    """

    version: int
    match_pair_idempotency: MatchPairIdempotency
    one_team_per_player: bool
    ranking_subject: RankingSubject
    tie_breakers: tuple[RankingMetric, ...]
    auto_register_players_on_match: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "match_pair_idempotency": self.match_pair_idempotency,
            "one_team_per_player": self.one_team_per_player,
            "ranking_subject": self.ranking_subject,
            "tie_breakers": list(self.tie_breakers),
            "auto_register_players_on_match": self.auto_register_players_on_match,
        }

    @classmethod
    def from_dict(cls, data: Any) -> LeagueRules:
        if not isinstance(data, dict):
            raise InvalidLeagueRulesError("League rules must be a JSON object")

        version = data.get("version")
        if version not in (1, 2, 3, 4, 5, 6):
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

        auto_register = cls._parse_auto_register_players_on_match(data, version)

        return cls(
            version=6,
            match_pair_idempotency=mpi,
            one_team_per_player=otpp,
            ranking_subject=ranking_subject,
            tie_breakers=tie_breakers,
            auto_register_players_on_match=auto_register,
        )

    @staticmethod
    def _parse_auto_register_players_on_match(data: dict[str, Any], version: int) -> bool:
        """Parse the participation gate flag in a version-aware way.

        v6 inputs carry `auto_register_players_on_match` directly.
        v5 inputs carry `require_allowlist` — invert.
        v4 inputs carry either `require_eligible_players` (preferred when
        present) or `require_allowlist` — invert.
        v1/v2/v3 default to `True` (today's default behavior).
        """
        if version == 6:
            value = data.get("auto_register_players_on_match")
            if value is None:
                return True
            if not isinstance(value, bool):
                raise InvalidLeagueRulesError(
                    "auto_register_players_on_match must be a boolean"
                )
            return value

        if version == 5:
            legacy = data.get("require_allowlist")
            if legacy is None:
                return True
            if not isinstance(legacy, bool):
                raise InvalidLeagueRulesError(
                    "require_allowlist must be a boolean"
                )
            return not legacy

        if version == 4:
            if "require_eligible_players" in data and data.get("require_eligible_players") is not None:
                legacy = data.get("require_eligible_players")
            else:
                legacy = data.get("require_allowlist")
            if legacy is None:
                return True
            if not isinstance(legacy, bool):
                raise InvalidLeagueRulesError(
                    "require_eligible_players / require_allowlist must be a boolean"
                )
            return not legacy

        return True

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

        Migrated existing DB rows have been upgraded through alembic 002
        (match_pair_idempotency \"none\"), 003 (ranking_subject=\"team\" /
        tie_breakers=[\"matches_won\"]), 004 (v3 with the `(player, OTPP=true)`
        rewrite), 005 (`require_eligible_players=false` / v4), 006
        (rename to `require_allowlist` / v5), and 007 (drop the
        `allowlist_entries` table and replace `require_allowlist` with
        `auto_register_players_on_match` with the boolean inverted) — together
        these reproduce v1/v2/v3/v4/v5 behavior byte-for-byte for every legal
        combo carried over.
        """
        return cls(
            version=6,
            match_pair_idempotency="once_per_league",
            one_team_per_player=True,
            ranking_subject="team",
            tie_breakers=("matches_won",),
            auto_register_players_on_match=True,
        )
