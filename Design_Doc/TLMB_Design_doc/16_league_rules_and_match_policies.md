# League rules and match policies

## Purpose

Leagues differ in how strictly they treat **repeat matchups** (same doubles pair vs same doubles pair) and, in the future, **roster constraints** (who may play, whether a player may appear on more than one team). This document defines a **versioned, per-league rules document** stored with the league, how it is set, and how **submit match** consults it—without requiring a new DB column for every new policy.

**Scope in the first implementation (v1 of `LeagueRules`):** persist rules on the league; enforce **match pair idempotency** (`none` vs `once_per_league`).

**Scope added in v2 of `LeagueRules`:** configurable ranking — `ranking_subject` (`"team"` vs `"player"`) and an ordered `tie_breakers` list (`matches_won`, `match_diff`, `games_won`, `games_lost`, `games_diff`, `win_pct`). Full specification lives in [17_configurable_ranking.md](17_configurable_ranking.md).

**Scope added in v3 of `LeagueRules`:** `one_team_per_player = false` is now legal (a player may belong to multiple teams) and a `(ranking_subject, one_team_per_player)` cross-rule is introduced: `ranking_subject = "player"` requires `one_team_per_player = false`. Full specification lives in [18_configurable_ranking_v3.md](18_configurable_ranking_v3.md).

**Scope added in v4/v5/v6 of `LeagueRules`:** `auto_register_players_on_match: bool` (v6+; supersedes v5 `require_allowlist`, which itself superseded v4 `require_eligible_players`) — when `false`, `SubmitMatchResultUseCase` rejects any submission whose four nicknames include one not on the league's roster (`players`). When `true` (the v6 default), missing nicknames are auto-registered as new `Player` rows during match submission. Full specification lives in [20_roster_pre_registration.md](20_roster_pre_registration.md).

**Scope added in v7 of `LeagueRules`:** `match_pair_idempotency: "once_per_day"`. The daily rule blocks duplicate unordered team-pair matches only within the league-local calendar day of match submission. The league-local day is computed from the top-level `League.league_timezone` field, stored as `leagues.league_timezone` and defaulting existing/omitted values to `America/Los_Angeles`.

**Out of scope until specified:** head-to-head tie-breakers, multi-set scoring.

**Mutability:** Rules are **fixed at league creation** (optional request body; otherwise product defaults). There is **no** host API to patch rules after creation in this version.

---

## Concepts

### LeagueRules (value object)

- **Owned by:** League aggregate (loaded and saved with the league row).
- **Serialized as:** JSON object in PostgreSQL `JSONB` on `leagues.rules`.
- **Versioning:** A required integer field `version` (started at `1`; current is `7`). Parsers accept unknown keys for forward compatibility but validate known keys strictly. v1–v6 inputs are silently upgraded to v7 (v1 inputs additionally have the v2 ranking defaults injected before the later upgrades; v4 inputs map the legacy `require_eligible_players` key to v5 `require_allowlist`, the v5→v6 step **inverts** that boolean and renames it to `auto_register_players_on_match`, and v7 adds `once_per_day`).
- **Fields (v7):**

| Field | Type (logical) | Meaning |
|-------|----------------|---------|
| `version` | int | Schema version; current is `7`. v1–v6 are accepted on input and upgraded transparently. |
| `match_pair_idempotency` | enum string | `none`: allow multiple matches between the same two teams. `once_per_league`: at most one match row per **unordered** team pair in the league. `once_per_day`: at most one match row per unordered team pair per league-local calendar day. |
| `one_team_per_player` | bool | `true` (default for new leagues): a player may belong to at most one team in the league; [`OneTeamPerPlayerPolicy`](05_aggregate_designs/league.md) is applied on `register_players_and_team`. `false`: a player may belong to multiple teams (e.g. partnered with Bob in one team and Charlie in another); the policy is skipped. The cross-rule below constrains which `(ranking_subject, one_team_per_player)` combos are legal. |
| `ranking_subject` | enum string (v2+) | `"team"` (default): rank one row per team. `"player"`: rank one row per player. **v3 cross-rule:** `ranking_subject = "player"` requires `one_team_per_player = false`. Equivalently, `one_team_per_player = true` forces `ranking_subject = "team"`. The combo `(player, OTPP=true)` is rejected with `InvalidLeagueRulesError`. See [18_configurable_ranking_v3.md](18_configurable_ranking_v3.md). |
| `tie_breakers` | list[enum string] (v2+) | Ordered, non-empty, no duplicates. Each entry is one of `matches_won`, `match_diff`, `games_won`, `games_lost`, `games_diff`, `win_pct`. The first entry is the primary metric; subsequent entries break ties. Default: `["matches_won"]`. |
| `auto_register_players_on_match` | bool (v6+) | `true` (default): missing nicknames on a submitted match are auto-registered as new `Player` rows during match submission (the v1–v4 behavior, preserved). `false`: `SubmitMatchResultUseCase` rejects submissions whose four nicknames include one not on the league's roster (`players`) with `RosterMembershipRequiredError`. Full specification: [20_roster_pre_registration.md](20_roster_pre_registration.md). |

**Migration defaults for existing leagues:** v1 -> v2 backfill via alembic 003 sets `version = 2`, `ranking_subject = "team"`, `tie_breakers = ["matches_won"]` so v2 behavior is byte-identical to v1 for previously-existing leagues. v2 -> v3 backfill via alembic 004 bumps `version` to `3` for every row and additionally rewrites every `(ranking_subject = "player", one_team_per_player = true)` row to `(ranking_subject = "team", one_team_per_player = true)` so the v3 cross-rule is satisfied — `tie_breakers` is preserved verbatim. v3 -> v4 backfill via alembic 005 introduces `require_eligible_players = false` on every row. v4 -> v5 backfill via alembic 006 renames `require_eligible_players` to `require_allowlist` (preserving the boolean value) and bumps `version` to `5`. v5 -> v6 backfill via alembic 007 renames `require_allowlist` to `auto_register_players_on_match` and **inverts** the boolean (so `require_allowlist = false` → `auto_register_players_on_match = true`, and `require_allowlist = true` → `auto_register_players_on_match = false`) — semantics are preserved, only the spelling and polarity flip; the same migration drops the `allowlist_entries` table after copying any v5 entries forward as `Player` rows on the same league. v6 -> v7 backfill via alembic 009 sets `rules.version = 7`, adds `leagues.league_timezone` with default `America/Los_Angeles`, and preserves every row's existing `match_pair_idempotency`. The legacy v1 backfill (alembic 002) for `match_pair_idempotency: "none"` and `one_team_per_player: true` continues to apply for rows that predate v1 rules. **New leagues** created without an explicit rules body use product defaults defined in application code: `version = 7`, `match_pair_idempotency = "once_per_day"`, `one_team_per_player = true`, `ranking_subject = "team"`, `tie_breakers = ["matches_won"]`, `auto_register_players_on_match = true`; `league_timezone` defaults to `America/Los_Angeles`.

### What counts as the “same matchup”

- After `register_players_and_team`, each side is a `TeamId`. Two teams form an **unordered pair**: the same matchup is `(team_a, team_b)` regardless of whether `team_a` was submitted as team1 or team2.
- Idempotency checks use **team IDs**, not nicknames, so implicit registration remains consistent with persisted teams.

### Where enforcement lives

- **Not** inside `Match.create`—the Match aggregate still only enforces `team1_id ≠ team2_id` and valid scores.
- **Application layer** (`SubmitMatchResultUseCase`), after teams are resolved and **before** `Match.create`, when rules require it:
  - `once_per_league`: call `MatchRepository.exists_match_for_team_pair(league_id, team1_id, team2_id)`.
  - `once_per_day`: compute the current date in `league.league_timezone`, convert local midnight bounds to UTC `[start, end)`, then call `MatchRepository.exists_match_for_team_pair_between(league_id, team1_id, team2_id, start, end)`.
- **Concurrency:** The use case already loads the league with `get_by_id_with_lock`, serializing concurrent submits for the same league; the existence check runs in the same transaction.

---

## Extensibility pattern (future rules)

Add new optional fields to the JSON schema and new **check steps** (or small checker objects) invoked from the submit use case in a **fixed order**. Prefer:

- **Declarative config** in JSON for simple toggles and lists (e.g. the roster auto-registration toggle, `auto_register_players_on_match`).
- **Repository queries** for constraints that depend on history (e.g. “already played today” using `created_at` and a timezone).
- **Parameterized domain behavior** for roster rules (e.g. pass a policy implementation into `register_players_and_team` based on `one_team_per_player`).

Potential future extensions:

| Rule | Config sketch | Enforcement sketch |
|------|---------------|-------------------|
| Head-to-head tie-breaker | `tie_breakers: [..., "head_to_head"]` | Requires sub-tournament reasoning across cycles; deferred until a stable algorithm is chosen |

---

## Persistence

See [12_persistence_strategy.md](12_persistence_strategy.md) for the `leagues.rules` column and ER diagram update.

---

## API and errors

See [13_api_contracts.md](13_api_contracts.md) for optional `rules` on `POST /leagues` and the HTTP mapping for duplicate team-pair submission.

---

## Related documents

- [20_roster_pre_registration.md](20_roster_pre_registration.md) — current (v6) specification of the unified roster pre-registration feature, the `auto_register_players_on_match` flag, and alembic migration 007 (which drops the v5 `allowlist_entries` table).
- [18_configurable_ranking_v3.md](18_configurable_ranking_v3.md) — v3 specification: cross-rule, OTPP=false read-path semantics, alembic 004 migration.
- [17_configurable_ranking.md](17_configurable_ranking.md) — v2 specification of `ranking_subject` and `tie_breakers`, kept as the v2 spec of record.
- [05_aggregate_designs/league.md](05_aggregate_designs/league.md) — League root carries `LeagueRules`; the one-team-per-player invariant is conditional on `LeagueRules.one_team_per_player`.
- [03_business_invariants.md](03_business_invariants.md) — Optional idempotency invariant; cross-invariant note when `one_team_per_player` is false.
- [09_application_use_cases.md](09_application_use_cases.md) — CreateLeague and SubmitMatchResult steps.
- [07_ports_and_repositories.md](07_ports_and_repositories.md) — `MatchRepository.exists_match_for_team_pair`.
