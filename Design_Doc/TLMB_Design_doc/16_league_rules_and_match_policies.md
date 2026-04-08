# League rules and match policies

## Purpose

Leagues differ in how strictly they treat **repeat matchups** (same doubles pair vs same doubles pair) and, in the future, **roster constraints** (who may play, whether a player may appear on more than one team). This document defines a **versioned, per-league rules document** stored with the league, how it is set, and how **submit match** consults it—without requiring a new DB column for every new policy.

**Scope in the first implementation:** persist rules on the league; enforce **match pair idempotency** (`none` vs `once_per_league`). **Out of scope until specified:** `once_per_calendar_day` (needs a stored day boundary, e.g. league IANA timezone), player allowlist, relaxing one-team-per-player (those are documented here as **future extensions**).

**Mutability:** Rules are **fixed at league creation** (optional request body; otherwise product defaults). There is **no** host API to patch rules after creation in this version.

---

## Concepts

### LeagueRules (value object)

- **Owned by:** League aggregate (loaded and saved with the league row).
- **Serialized as:** JSON object in PostgreSQL `JSONB` on `leagues.rules`.
- **Versioning:** A required integer field `version` (start at `1`). Parsers accept unknown keys for forward compatibility but validate known keys strictly.
- **First-version fields:**

| Field | Type (logical) | Meaning |
|-------|----------------|---------|
| `version` | int | Schema version; must be `1` for v1 |
| `match_pair_idempotency` | enum string | `none`: allow multiple matches between the same two teams. `once_per_league`: at most one match row per **unordered** team pair in the league. |
| `one_team_per_player` | bool | `true` (default): current behavior—[`OneTeamPerPlayerPolicy`](05_aggregate_designs/league.md) applies. `false` (future): allow a player on multiple teams; **read models** that assume a single team per player must be updated before enabling. |

**Migration defaults for existing leagues:** Backfill `match_pair_idempotency: "none"` and `one_team_per_player: true` so behavior matches pre-rules deployments. **New leagues** created without an explicit rules body use product defaults defined in application code (recommended: `once_per_league` for new leagues only—document the choice in code comments).

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

- [05_aggregate_designs/league.md](05_aggregate_designs/league.md) — League root carries `LeagueRules`; invariant wording for one-team-per-player becomes conditional.
- [03_business_invariants.md](03_business_invariants.md) — Optional idempotency invariant; cross-invariant note when `one_team_per_player` is false.
- [09_application_use_cases.md](09_application_use_cases.md) — CreateLeague and SubmitMatchResult steps.
- [07_ports_and_repositories.md](07_ports_and_repositories.md) — `MatchRepository.exists_match_for_team_pair`.
