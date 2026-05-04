# League rules and match policies

## Purpose

Leagues differ in how strictly they treat **repeat matchups** (same doubles pair vs same doubles pair) and, in the future, **roster constraints** (who may play, whether a player may appear on more than one team). This document defines a **versioned, per-league rules document** stored with the league, how it is set, and how **submit match** consults it—without requiring a new DB column for every new policy.

**Scope in the first implementation (v1 of `LeagueRules`):** persist rules on the league; enforce **match pair idempotency** (`none` vs `once_per_league`).

**Scope added in v2 of `LeagueRules`:** configurable ranking — `ranking_subject` (`"team"` vs `"player"`) and an ordered `tie_breakers` list (`matches_won`, `match_diff`, `games_won`, `games_lost`, `games_diff`, `win_pct`). Full specification lives in [17_configurable_ranking.md](17_configurable_ranking.md).

**Out of scope until specified:** `once_per_calendar_day` (needs a stored day boundary, e.g. league IANA timezone), player allowlist, relaxing one-team-per-player (those are documented here as **future extensions**), head-to-head tie-breakers, multi-set scoring.

**Mutability:** Rules are **fixed at league creation** (optional request body; otherwise product defaults). There is **no** host API to patch rules after creation in this version.

---

## Concepts

### LeagueRules (value object)

- **Owned by:** League aggregate (loaded and saved with the league row).
- **Serialized as:** JSON object in PostgreSQL `JSONB` on `leagues.rules`.
- **Versioning:** A required integer field `version` (started at `1`; current is `2`). Parsers accept unknown keys for forward compatibility but validate known keys strictly. v1 inputs are silently upgraded to v2 by injecting the v2 ranking defaults.
- **Fields (v2):**

| Field | Type (logical) | Meaning |
|-------|----------------|---------|
| `version` | int | Schema version; current is `2`. v1 is accepted on input and upgraded transparently. |
| `match_pair_idempotency` | enum string | `none`: allow multiple matches between the same two teams. `once_per_league`: at most one match row per **unordered** team pair in the league. |
| `one_team_per_player` | bool | **v2: locked to `true`**. `LeagueRules.from_dict` rejects any other value. [`OneTeamPerPlayerPolicy`](05_aggregate_designs/league.md) applies to every league. v3 will accept `false` (a player on multiple teams), at which point **read models** that assume a single team per player must be updated. |
| `ranking_subject` | enum string (v2+) | `"team"` (default): rank one row per team. `"player"`: rank one row per player. No `(ranking_subject, one_team_per_player)` cross-rule in v2 — `one_team_per_player` is locked to `true`, which makes any pairing trivially valid. v3 introduces a cross-rule when OTPP=false ships — see [17](17_configurable_ranking.md). |
| `tie_breakers` | list[enum string] (v2+) | Ordered, non-empty, no duplicates. Each entry is one of `matches_won`, `match_diff`, `games_won`, `games_lost`, `games_diff`, `win_pct`. The first entry is the primary metric; subsequent entries break ties. Default: `["matches_won"]`. |

**Migration defaults for existing leagues:** v1 -> v2 backfill via alembic 003 sets `version = 2`, `ranking_subject = "team"`, `tie_breakers = ["matches_won"]` so v2 behavior is byte-identical to v1 for previously-existing leagues. The legacy v1 backfill (alembic 002) for `match_pair_idempotency: "none"` and `one_team_per_player: true` continues to apply for rows that predate v1 rules. **New leagues** created without an explicit rules body use product defaults defined in application code (recommended: `once_per_league`, `ranking_subject = "team"`, `tie_breakers = ["matches_won"]` for new leagues only—document the choice in code comments).

### What counts as the “same matchup”

- After `register_players_and_team`, each side is a `TeamId`. Two teams form an **unordered pair**: the same matchup is `(team_a, team_b)` regardless of whether `team_a` was submitted as team1 or team2.
- Idempotency checks use **team IDs**, not nicknames, so implicit registration remains consistent with persisted teams.

### Where enforcement lives

- **Not** inside `Match.create`—the Match aggregate still only enforces `team1_id ≠ team2_id` and valid scores.
- **Application layer** (`SubmitMatchResultUseCase`), after teams are resolved and **before** `Match.create`, when rules require it: call `MatchRepository.exists_match_for_team_pair(league_id, team1_id, team2_id)`.
- **Concurrency:** The use case already loads the league with `get_by_id_with_lock`, serializing concurrent submits for the same league; the existence check runs in the same transaction.

---

## Extensibility pattern (future rules)

Add new optional fields to the JSON schema and new **check steps** (or small checker objects) invoked from the submit use case in a **fixed order**. Prefer:

- **Declarative config** in JSON for simple toggles and lists (e.g. allowlist of normalized nicknames).
- **Repository queries** for constraints that depend on history (e.g. “already played today” using `created_at` and a timezone).
- **Parameterized domain behavior** for roster rules (e.g. pass a policy implementation into `register_players_and_team` based on `one_team_per_player`).

Planned extensions (design placeholders only):

| Rule | Config sketch | Enforcement sketch |
|------|---------------|-------------------|
| Once per calendar day | `match_pair_idempotency: "once_per_day"`, `league_timezone: "America/Los_Angeles"` | `MatchRepository` method filtering by local date of `created_at` |
| Player pre-allowlist | `allowed_nicknames_normalized: string[]` | Before or after nickname normalization, reject if any of the four nicknames not in set |
| Multiple teams per player | `one_team_per_player: false` | Skip or replace `OneTeamPerPlayerPolicy` in `register_players_and_team`; update `GetStandingsByPlayer` / `GetMatchHistoryByPlayer` (today they use `next(...)` and assume one team) |

---

## Persistence

See [12_persistence_strategy.md](12_persistence_strategy.md) for the `leagues.rules` column and ER diagram update.

---

## API and errors

See [13_api_contracts.md](13_api_contracts.md) for optional `rules` on `POST /leagues` and the HTTP mapping for duplicate team-pair submission.

---

## Related documents

- [17_configurable_ranking.md](17_configurable_ranking.md) — full v2 specification of `ranking_subject` and `tie_breakers`, including the polymorphic standings response and the v3 forward-compatibility plan.
- [05_aggregate_designs/league.md](05_aggregate_designs/league.md) — League root carries `LeagueRules`; invariant wording for one-team-per-player becomes conditional.
- [03_business_invariants.md](03_business_invariants.md) — Optional idempotency invariant; cross-invariant note when `one_team_per_player` is false.
- [09_application_use_cases.md](09_application_use_cases.md) — CreateLeague and SubmitMatchResult steps.
- [07_ports_and_repositories.md](07_ports_and_repositories.md) — `MatchRepository.exists_match_for_team_pair`.
