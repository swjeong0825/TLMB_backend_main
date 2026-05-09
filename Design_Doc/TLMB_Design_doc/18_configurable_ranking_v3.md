# Configurable league ranking — v3

## Purpose

V3 is the next iteration of `LeagueRules` after [v2](17_configurable_ranking.md) (currently in production). V2 added configurable ranking (`ranking_subject` + ordered `tie_breakers`) but locked `one_team_per_player` to `true`, which made `ranking_subject = "player"` mathematically equivalent to `ranking_subject = "team"`. V3 unlocks `one_team_per_player = false`, introduces the first `(ranking_subject, one_team_per_player)` cross-rule, and ships the read-path revisions that make player-subject leagues genuinely distinct from team-subject leagues.

This document is the v3 spec. It supersedes the "Forward-compatibility note (planned for v3)" in [17_configurable_ranking.md](17_configurable_ranking.md) §line 257.

**Scope in this implementation (v3 of LeagueRules):**

- Loosen `LeagueRules.from_dict` so `one_team_per_player = false` is accepted.
- Introduce the first cross-rule: `ranking_subject = "player"` requires `one_team_per_player = false`. Equivalently, `one_team_per_player = true` forces `ranking_subject = "team"`.
- Bump `LeagueRules.version` to `3`. v1 and v2 inputs continue to be accepted on read and upgraded transparently.
- Update read paths that today assume "a player belongs to at most one team":
  - `GetStandingsByPlayerUseCase` returns **all** of the player's team rows under `(team, OTPP=false)` (one entry per team).
  - `GetMatchHistoryByPlayerUseCase` returns matches across **all** of the player's teams (union, deduped by `match_id`).
- Ship an alembic migration (`004`) that auto-rewrites every existing `(player, OTPP=true)` row to `(team, OTPP=true)`, preserving `tie_breakers` verbatim.
- Re-introduce a frontend OTPP control on the create-league form, with a client-side coupling that mirrors the server-side cross-rule.

**Out of scope until specified:**

- Multi-set / per-game scoring (still one `SetScore` per match).
- Head-to-head tie-breakers.
- Mid-league rule edits (rules remain immutable after creation).
- Mutable rules / a host PATCH endpoint.
- Dense rank as a configurable option — standard-competition rank stays hard-coded.
- A submit-time check for a player on team1 *and* on a different team that is team2 — already enforced by the existing `SamePlayerOnBothTeamsError` (compares nicknames, runs before any aggregate is loaded). v3 trusts this, the calculator's same-player-on-both-sides guard becomes a defense-in-depth check only.

**Mutability:** Unchanged from v1/v2 — rules are fixed at league creation.

---

## What changes from v2

### Validation matrix

| Combo | v2 (today, prod) | v3 (this doc) | Notes |
|---|---|---|---|
| `(team, OTPP=true)` | legal | legal | Default for new leagues; unchanged byte-for-byte. |
| `(player, OTPP=true)` | legal but mathematically equivalent to `(team, OTPP=true)` | **illegal** (cross-rule rejection) | Existing prod rows are auto-rewritten to `(team, OTPP=true)` by alembic 004. |
| `(team, OTPP=false)` | illegal (OTPP=false rejected) | **legal** | A player may belong to multiple teams; team rows aggregate match outcomes per team. |
| `(player, OTPP=false)` | illegal (OTPP=false rejected) | **legal** | Player rows aggregate match outcomes across every team the player belongs to. This is the case where v2's player-subject path becomes genuinely useful. |

### Why introduce the cross-rule now

`(player, OTPP=true)` produces standings that are *mathematically equivalent* to `(team, OTPP=true)` (every teammate has identical metric tuples; see [17_configurable_ranking.md §"Worked example"](17_configurable_ranking.md#worked-example-equivalence-under-otpptrue)). Allowing it in v3 once `OTPP=false` exists would offer two ways to express "rank by team" with no observable difference, increasing schema ambiguity for no UX win. Rejecting it converges the schema on a state where every legal combo conveys distinct information.

### Why `(team, OTPP=false)` is legal and meaningful

Under OTPP=false, a player can be on multiple teams (e.g. partnered with Bob in one team, and with Charlie in another). Team-subject standings still rank one row per team. Each team's metrics aggregate only that team's matches. This is what most "casual round-robin where partners rotate" leagues actually want.

### Migration impact for existing leagues

V2 leagues all have `one_team_per_player = true` (locked at validation time), so the only existing combo that becomes illegal under v3 is `(player, OTPP=true)`. Migration 004 rewrites every such row to `(team, OTPP=true)`:

- `ranking_subject` flips from `"player"` to `"team"`.
- `tie_breakers` is preserved verbatim — host metric choices are not lost.
- `one_team_per_player` and `match_pair_idempotency` are untouched.
- `version` is bumped to `3` for every row (including unaffected rows), so `LeagueRules.from_dict` does not re-validate them on every read.

Affected leagues' standings will visibly change shape — rows collapse from one-per-player back to one-per-team, halving the row count. The v3 release notes must call this out so league hosts are not surprised.

---

## LeagueRules v3 schema

```json
{
  "version": 3,
  "match_pair_idempotency": "once_per_league",
  "one_team_per_player": false,
  "ranking_subject": "team",
  "tie_breakers": ["matches_won", "games_diff"]
}
```

| Field | Type | Allowed values | Default for new leagues |
|---|---|---|---|
| `version` | int | `3` strict; `1` and `2` accepted on input and upgraded | `3` |
| `match_pair_idempotency` | str | `"none"`, `"once_per_league"` | `"once_per_league"` (unchanged) |
| `one_team_per_player` | bool | `true` or `false` | `true` (unchanged from v1/v2 product default) |
| `ranking_subject` | str | `"team"`, `"player"` | `"team"` (unchanged from v2) |
| `tie_breakers` | list[str] | non-empty; entries from `matches_won`, `match_diff`, `games_won`, `games_lost`, `games_diff`, `win_pct`; no duplicates | `["matches_won"]` (unchanged from v2) |

### Defaults rationale

The product default for new leagues stays `(team, OTPP=true, ["matches_won"])` — byte-identical to v2 defaults. v3 only widens the legal input set; it does not change what the create-league form sends when the user accepts defaults.

### Validation rules

`LeagueRules.from_dict` strictly validates v3 inputs:

1. `version` must be `1`, `2`, or `3`.
   - v1 inputs inject `ranking_subject="team"`, `tie_breakers=["matches_won"]`, then upgrade to v3.
   - v2 inputs are revalidated against the v3 cross-rule, then upgrade to v3 (a v2 row with `(player, OTPP=true)` would be rejected here, but the only v2 rows actually in the database have already been rewritten by migration 004 before any upgrade-on-read happens).
   - v3 inputs are validated as-is.
2. `match_pair_idempotency` must be `"none"` or `"once_per_league"` (unchanged).
3. `one_team_per_player` must be a boolean (no value-restriction; both `true` and `false` are legal).
4. `ranking_subject` must be `"team"` or `"player"`.
5. `tie_breakers` must be a non-empty list of allowed metrics with no duplicates.
6. **Cross-rule (new in v3):** if `ranking_subject == "player"` and `one_team_per_player is True`, raise `InvalidLeagueRulesError`.

The cross-rule message text should be explicit and actionable: e.g. `"ranking_subject='player' requires one_team_per_player=false; pick (team, OTPP=true) or (player, OTPP=false)"`.

---

## Standings response shape

**Unchanged from v2.** The response is still polymorphic on `subject_kind`, every row carries every metric, and the top-level `tie_breakers` is a verbatim copy of `LeagueRules.tie_breakers`. See [17_configurable_ranking.md §"Standings response shape (polymorphic)"](17_configurable_ranking.md#standings-response-shape-polymorphic) for the full schema.

What's new in v3 is what the values *mean* under OTPP=false:

- For `ranking_subject == "team"`: each team row aggregates only the matches that team played. A player who is on multiple teams contributes their per-match score to whichever team they were partnered with for that specific match.
- For `ranking_subject == "player"`: each player row aggregates the player's per-match scores across **every team** they belong to. Partners may differ across matches; the player accumulates wins/losses/games regardless.

---

## Read-path contracts under OTPP=false

The endpoints `GET /leagues/{id}/standings/by-player` and `GET /leagues/{id}/matches/by-player` resolve a player by nickname. Under OTPP=true these were trivially scoped to "the player's one team". Under OTPP=false the contract widens.

### `GET /leagues/{id}/standings/by-player`

| `ranking_subject` | OTPP | Behavior |
|---|---|---|
| `"team"` | `true` | Returns the single row of the player's one team (unchanged from v2). |
| `"team"` | `false` | Returns **all** rows for every team the player belongs to. The `standings` array may have multiple entries. |
| `"player"` | `false` | Returns the single row for the player's own player-subject entry. |
| `"player"` | `true` | **Not reachable** — rejected by the cross-rule at create time. |

The empty-result case (player exists but has no team — e.g. all their teams were deleted) still returns an empty `standings` array.

### `GET /leagues/{id}/matches/by-player`

| OTPP | Behavior |
|---|---|
| `true` | Returns matches for the player's one team (unchanged from v2). |
| `false` | Returns the **union** of matches across every team the player belongs to, deduped by `match_id`, sorted by `created_at` descending. |

To support the OTPP=false case efficiently, `MatchRepository` gains a new method `get_all_by_player(league_id, player_id, team_ids) -> list[Match]`. The implementation is a single SQL query: `WHERE league_id = :lid AND (team1_id = ANY(:tids) OR team2_id = ANY(:tids))`. Application-layer aggregation across multiple `get_all_by_team` calls is also acceptable but less efficient.

---

## Calculation flow

Identical structure to v2 (see [17_configurable_ranking.md §"Calculation flow"](17_configurable_ranking.md#calculation-flow)). The `_compute_for_players` branch in `StandingsCalculator` is already implemented to aggregate per-match outcomes across every team a player belongs to (`teams_for_player[player_id]` is a `set`), so v2 shipped the OTPP=false-correct algorithm a release early. V3 simply validates that this branch now runs against genuinely-distinct partner sets in real data.

The same-player-on-both-sides guard inside the calculator (`if t1 in team_ids and t2 in team_ids: continue`) becomes a defense-in-depth check in v3. The primary defense is the existing submit-time `SamePlayerOnBothTeamsError`, which compares nicknames *before* any aggregate is loaded — see `SubmitMatchResultUseCase`. Persisted match data should never trigger the calculator guard; if it does, that indicates a bug or a hand-edit of the `matches` table.

---

## Worked example: distinct player rows under OTPP=false

Four players, three matches, OTPP=false, `ranking_subject = "player"`, `tie_breakers = ["matches_won", "games_diff"]`:

| Match | Team 1 | Team 2 | Score |
|---|---|---|---|
| 1 | Alice + Bob | Charlie + Dan | 6-4 |
| 2 | Alice + Charlie | Bob + Dan | 6-2 |
| 3 | Bob + Charlie | Alice + Dan | 6-3 |

Per-player aggregation (each player credited once per match they appeared in):

| Player | Matches played | Wins | Losses | Games for | Games against | Diff |
|---|---|---|---|---|---|---|
| Alice | 3 | 2 | 1 | 6+6+3 = 15 | 4+2+6 = 12 | +3 |
| Bob | 3 | 2 | 1 | 6+2+6 = 14 | 4+6+3 = 13 | +1 |
| Charlie | 3 | 1 | 2 | 4+6+6 = 16 | 6+2+3 = 11 | +5 |
| Dan | 3 | 0 | 3 | 4+2+3 = 9 | 6+6+6 = 18 | -9 |

After sort by `(matches_won desc, games_diff desc)`:

| Rank | Player | Wins | Diff |
|---|---|---|---|
| 1 | Alice | 2 | +3 |
| 1 | Bob | 2 | +1 |
| 3 | Charlie | 1 | +5 |
| 4 | Dan | 0 | -9 |

Note Alice and Bob tie on `matches_won` and **do not** tie on `games_diff` — under v2's OTPP=true equivalence example, teammates always shared a rank. Under v3 OTPP=false they don't, because they didn't always partner together. This is the case the v2 player-subject branch was built to serve.

For comparison, the same matches under `ranking_subject = "team"`, OTPP=false:

| Rank | Team | Wins | Diff |
|---|---|---|---|
| 1 | Alice + Bob | 1 | +2 |
| 1 | Alice + Charlie | 1 | +4 |
| 1 | Bob + Charlie | 1 | +3 |
| 4 | Charlie + Dan | 0 | -2 |
| 4 | Bob + Dan | 0 | -4 |
| 4 | Alice + Dan | 0 | -3 |

Six rows — one per distinct partnership — none of which are equivalent to the per-player table above.

---

## Migration plan (v2 -> v3)

A new alembic revision (`004_leagues_rules_v3.py`) does the rewrite + version bump in two `UPDATE` statements:

```sql
-- Rewrite (player, OTPP=true) → (team, OTPP=true), preserving tie_breakers.
UPDATE leagues
SET rules = rules || jsonb_build_object('version', 3, 'ranking_subject', 'team')
WHERE (rules->>'version')::int IN (1, 2)
  AND (rules->>'ranking_subject') = 'player'
  AND (rules->>'one_team_per_player')::bool = true;

-- Bump everyone else (v1 or v2) to v3 in place.
UPDATE leagues
SET rules = rules || jsonb_build_object('version', 3)
WHERE (rules->>'version')::int IN (1, 2);
```

No DDL — `leagues.rules` stays JSONB. The migration is idempotent (re-running on v3 rows is a no-op because the `WHERE` clause filters by `version IN (1, 2)`).

### Downgrade contract

The downgrade resets `version` to `2` for every row where `version = 3`:

```sql
UPDATE leagues
SET rules = rules || jsonb_build_object('version', 2)
WHERE (rules->>'version')::int = 3;
```

The `(player, OTPP=true) → (team, OTPP=true)` rewrite from upgrade is **not reversed** by downgrade. A row that was `(player, OTPP=true)` in v2 cannot be recovered after upgrade because the original `ranking_subject` value is overwritten in place. The migration's docstring documents this as a one-way data change. Operators who need a recovery path must take a manual JSONB snapshot of the `leagues.rules` column before running the upgrade.

This decision (best-effort downgrade rather than blocking-downgrade or snapshot-table) was made because:

- v2 standings for `(player, OTPP=true)` are mathematically equivalent to `(team, OTPP=true)` standings, so the user-visible information is preserved by the rewrite — only the rendering shape changes.
- A blocking downgrade would prevent rollback in a production incident, which is a worse failure mode than data shape regression.
- A snapshot table adds a one-time schema artifact that has to be cleaned up later, increasing migration complexity for a value-objects column whose history is rarely meaningful.

---

## Forward-compatibility (post-v3)

V3 leaves the schema in a state where every legal combo conveys distinct information and every illegal combo is enforced uniformly. Future versions will most likely add:

- Head-to-head as a tie-breaker metric (requires sub-tournament reasoning).
- Multi-set scoring (requires changing `Match` value objects, not `LeagueRules`).
- Per-day idempotency (`once_per_calendar_day`) once a league timezone is stored.

None of these change the v3 ranking-config validation matrix. They extend orthogonal axes (metrics, score shape, match-pair rules) and can ship without bumping `LeagueRules.version` if they introduce only additional optional fields, or as v4 if they meaningfully change validation.

---

## Implementation impact

Files edited or created in this v3 release. See file-level TODOs and the design-doc cross-references for context.

### Backend domain layer

| File | Change |
|---|---|
| `backend_main/app/domain/aggregates/league/league_rules.py` | Bump `default_for_new_league` to `version=3`. In `from_dict`: accept `version ∈ {1, 2, 3}`, drop the `otpp is True` strict check, add the `(player, OTPP=true)` cross-rule rejection, always emit `version=3` on the constructed object. Remove the `# TODO(v3-ranking-tightening)` comments. |
| `backend_main/app/domain/aggregates/league/aggregate_root.py` | No code change. `register_players_and_team` already gates `OneTeamPerPlayerPolicy` on `self.rules.one_team_per_player`. |
| `backend_main/app/domain/aggregates/league/policies.py` | No change. |
| `backend_main/app/domain/services/standings_calculator.py` | Replace the `# TODO(v3-ranking-tightening)` comment with a v3 explanation. Code unchanged — the `_compute_for_players` branch is already OTPP=false-correct. The same-player-on-both-sides guard (line 184) is documented as defense-in-depth; the primary defense is `SamePlayerOnBothTeamsError` at submit time. |
| `backend_main/app/domain/aggregates/match/repository.py` | Add abstract method `get_all_by_player(league_id, player_id, team_ids) -> list[Match]` (used by `GetMatchHistoryByPlayerUseCase` under OTPP=false). |

### Backend application layer

| File | Change |
|---|---|
| `backend_main/app/application/use_cases/get_standings_by_player_use_case.py` | Replace the `next(...)` team lookup with a set-comprehension that collects every team the player belongs to, then filters `all_entries` by `e.team_id in player_team_ids`. Remove the `# TODO(v3-ranking-tightening)` comment. |
| `backend_main/app/application/use_cases/get_match_history_by_player_use_case.py` | Replace the `next(...)` team lookup + single `get_all_by_team` call with a single `get_all_by_player(league_id, player_id, team_ids)` call. Dedupe by `match_id` (the new repo method does this server-side). |
| `backend_main/app/application/use_cases/submit_match_result_use_case.py` | No change. The existing `SamePlayerOnBothTeamsError` check already prevents the only pathological OTPP=false case the calculator's defense-in-depth guard would catch. |
| `backend_main/app/application/use_cases/create_league_use_case.py` | No change. |

### Backend infrastructure

| File | Change |
|---|---|
| `backend_main/alembic/versions/004_leagues_rules_v3.py` | **NEW.** Implements the two `UPDATE` statements above. `revision = "004"`, `down_revision = "003"`. Docstring documents the irreversible `(player, OTPP=true) → (team, OTPP=true)` rewrite. |
| `backend_main/app/infrastructure/persistence/repositories/match_repository.py` | Implement `get_all_by_player`. SQL: `SELECT … FROM matches WHERE league_id = :lid AND (team1_id = ANY(:tids) OR team2_id = ANY(:tids))`. |

### Backend API layer

| File | Change |
|---|---|
| `backend_main/app/api/schemas/league_schemas.py` | Rename `LeagueRulesV2Request` → `LeagueRulesV3Request`. Bump `version: Literal[1, 2]` → `Literal[1, 2, 3]`. Update the docstring to describe the cross-rule (`InvalidLeagueRulesError → 422`) instead of the OTPP=true lock. |
| `backend_main/app/api/routers/league_router.py` | Update the import for the renamed request class. No behavior change. |

### Frontend

| File | Change |
|---|---|
| `frontend/frontend_vanilla/create-league/index.html` | Insert a new `<select name="one_team_per_player">` block in `details.create-league-advanced`, positioned between the `match_pair_idempotency` and `ranking_subject` controls. |
| `frontend/frontend_vanilla/js/create-league.js` | In `buildPayload`, send `version: 3` and the actual OTPP boolean. Add a `change`-event handler that enforces the cross-rule client-side: setting `ranking_subject = "player"` forces OTPP=false; setting OTPP=true forces `ranking_subject = "team"`. Remove the `// TODO(v3-ranking-tightening)` comment. |
| `frontend/frontend_vanilla/js/i18n.js` | Add new keys (en + ko): `createLeague.labelOneTeamPerPlayer`, `createLeague.optionOTPPTrue`, `createLeague.optionOTPPFalse`, `createLeague.crossRuleHint`. The legacy `createLeague.oneTeamPerPlayer` key may be deprecated. |
| `frontend/frontend_vanilla/js/chat.js` | No change. The standings renderer is already polymorphic on `subject_kind` and tie-breaker-aware. |
| `frontend/frontend_vanilla/js/user-facing-errors.js` | Optional: add a friendly mapping for the `InvalidLeagueRulesError` cross-rule message text, as a backstop if the client-side coupling is bypassed. |

### Chat-to-intent server

| File | Change |
|---|---|
| `chat_to_intent_server/design_doc/configurable_ranking_v2.md` | Rename to `configurable_ranking_v3.md` and update the §"Forward-compatibility (v3)" section to reflect "shipped". |
| `chat_to_intent_server_fastapi/design_doc/02_read_only_backend_endpoints.md` | Add a note under `GET /leagues/{league_id}/standings/by-player` that under v3 the endpoint may return multiple rows when the resolved player belongs to multiple teams. |
| `chat_to_intent_server_fastapi/app/intents/handlers/get_standings_handler.py` | No change. Verbatim forwarder. |
| `chat_to_intent_server_fastapi/app/intents/handlers/get_standings_by_player_handler.py` | No change. Verbatim forwarder; tolerates ≥1 rows already. |
| `chat_to_intent_server_fastapi/app/application/intent_identification/intent_registry.py` | No change. Descriptions are already rule-agnostic. |

### Other backend design docs touched

| File | Change |
|---|---|
| `backend_main/Design_Doc/TLMB_Design_doc/16_league_rules_and_match_policies.md` | Drop "v2 locks…" wording on lines 9, 23, 30, 34. The cross-rule moves into the main rules table. |
| `backend_main/Design_Doc/TLMB_Design_doc/17_configurable_ranking.md` | Replace the "Forward-compatibility note (planned for v3)" section with a one-line reference to this document. |
| `backend_main/Design_Doc/TLMB_Design_doc/13_api_contracts.md` | Bump example `rules` body to v3, refresh error wording to match the v3 cross-rule. |
| `backend_main/Design_Doc/TLMB_Design_doc/06_domain_services.md` | Rewrite the `ranking_subject == "player"` paragraph to describe OTPP=false credit semantics. |
| `backend_main/Design_Doc/TLMB_Design_doc/05_aggregate_designs/league.md` | Drop "v2 locks…" wording on lines 50, 72, 141, 146. |
| `backend_main/Design_Doc/TLMB_Design_doc/03_business_invariants.md` | Update line 32's reference to the v3 release notes; the conditional invariant statement (line 27) stays. |

---

## Test matrix

### Domain

`backend_main/tests/domain/test_league_rules.py`:

- Flip `test_from_dict_v1_input_with_otpp_false_is_rejected` → `test_from_dict_v1_input_with_otpp_false_upgrades_to_v3`.
- Flip `test_from_dict_rejects_otpp_false_with_team_subject` → `test_from_dict_accepts_team_subject_with_otpp_false`.
- Flip `test_from_dict_rejects_otpp_false_with_player_subject` → `test_from_dict_accepts_player_subject_with_otpp_false`.
- Flip `test_from_dict_accepts_player_subject_with_otpp_true` → `test_from_dict_rejects_player_subject_with_otpp_true` (the new cross-rule).
- Add `test_from_dict_v2_input_upgrades_to_v3`.
- Add `test_default_for_new_league_is_v3`.

`backend_main/tests/domain/test_league_aggregate.py`:

- Add: `register_players_and_team` allows the same player on a second team when `rules.one_team_per_player is False`.
- Verify: same operation still raises `TeamConflictError` when OTPP=true (regression).

`backend_main/tests/domain/test_standings_calculator.py`:

- Add the worked-example test from §"Worked example" above (4 players, 3 matches, OTPP=false, partner rotation produces non-equivalent rows).

### Application

`backend_main/tests/application/test_get_standings_by_player_use_case.py`:

- Existing OTPP=true tests stay green (regression).
- Add: `(team, OTPP=false)` with a player on 2 teams returns 2 rows.
- Add: `(player, OTPP=false)` returns 1 row (the player's own row).

`backend_main/tests/application/test_get_match_history_use_case.py` (or its by-player counterpart):

- Add: under OTPP=false, a player on 2 teams sees matches from both teams in the result, deduped by `match_id`.

### Integration / migration

`backend_main/tests/integration/test_migration_004_leagues_rules_v3.py` (NEW):

- Seed three rows: `(team, OTPP=true, version=2)`, `(player, OTPP=true, version=2)`, `(team, OTPP=true, version=2, tie_breakers=["games_won","games_diff"])`.
- Run upgrade. Assert row 2 is rewritten to `team`, all rows have `version=3`, row 3's `tie_breakers` preserved verbatim.
- Idempotency: re-run upgrade, assert no change.
- Downgrade: assert all rows back to `version=2`; assert row 2 still has `ranking_subject="team"` (irreversible by design).

`backend_main/tests/integration/test_migration_003_leagues_rules_v2.py`:

- No change. Stays as a regression for migration 003.

### E2E

`backend_main/tests/e2e/test_league_api.py`:

- Flip `test_create_league_with_otpp_false_returns_422` → `test_create_league_with_otpp_false_succeeds`.
- Add `test_create_league_with_player_subject_and_otpp_true_returns_422` (new cross-rule).
- Add `test_create_league_with_player_subject_and_otpp_false_succeeds`.
- Add `test_v2_rules_input_upgrades_to_v3` (smoke test for transparent upgrade).

### Chat-to-intent server

`chat_to_intent_server/chat_to_intent_server_fastapi/tests/e2e/test_read_intents.py`:

- If any test asserts a single-element `standings` array for the by-player path, broaden to allow ≥1.

---

## Verification checklist (gate before merging)

- [ ] All v2 tests still green (v2 acceptance is preserved on input).
- [ ] New v3 cross-rule tests green (`test_from_dict_rejects_player_subject_with_otpp_true`).
- [ ] Migration 004 idempotency + downgrade tests green.
- [ ] E2E: create `(team, OTPP=false)` league → submit Alice+Bob vs Charlie+Dan, then Alice+Eve vs Frank+Charlie → standings reflect per-team aggregation.
- [ ] E2E: create `(player, OTPP=false)` league → same submissions → Alice's `wins`/`losses` aggregate across both partnerships, distinct from her partners.
- [ ] E2E: create attempt with `(player, OTPP=true)` → 422 `InvalidLeagueRulesError`.
- [ ] Frontend manual: setting `ranking_subject="player"` disables OTPP=true; setting OTPP=true disables `ranking_subject="player"`.
- [ ] Existing prod leagues with `(player, OTPP=true)` are auto-rewritten to `(team, OTPP=true)` on migration; `tie_breakers` preserved.
- [ ] Release notes draft mentions the visible row-shape change for affected leagues.

---

## Rollout

Single coordinated PR (matches v2's lockstep rollout). All of:

1. Design docs updated.
2. Backend domain + application + API changes merged.
3. Migration 004 included.
4. Frontend OTPP control + coupling shipped.
5. Chat-to-intent server design docs updated (no code changes).

Frontend, backend, and migration all ship in the same release because old API clients sending `version: 2` continue to work (transparent upgrade), so there is no client-coordination risk for the v3 backend rollout. The only externally-visible change is the new OTPP control on the create-league form and the row-shape change for `(player, OTPP=true)` leagues, both of which are guarded by release notes.

---

## Related documents

- [17_configurable_ranking.md](17_configurable_ranking.md) — v2 specification. v3 supersedes its "Forward-compatibility note (planned for v3)" section.
- [16_league_rules_and_match_policies.md](16_league_rules_and_match_policies.md) — overall LeagueRules policy framework.
- [06_domain_services.md](06_domain_services.md) — `StandingsCalculator` algorithm notes.
- [05_aggregate_designs/league.md](05_aggregate_designs/league.md) — League aggregate root and `LeagueRules` value object.
- [13_api_contracts.md](13_api_contracts.md) — endpoint contracts.
- [03_business_invariants.md](03_business_invariants.md) — invariants table; the conditional one-team-per-player invariant becomes meaningfully conditional in v3.
- [12_persistence_strategy.md](12_persistence_strategy.md) — `leagues.rules` JSONB column. v3 reuses the column unchanged; only its in-flight content shape changes.
