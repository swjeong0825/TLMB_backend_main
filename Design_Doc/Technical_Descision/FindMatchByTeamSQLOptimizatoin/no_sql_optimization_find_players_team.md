# No SQL Optimization: `GetMatchHistoryByPlayerUseCase` — Finding the Player's Team

## Context

After resolving the player by nickname, the use case needs the player's `team_id` before
it can query matches. This lookup currently loads the **entire league roster** (all players
and all teams) into memory and resolves both lookups in Python.

**Current flow (`get_match_history_by_player_use_case.py`, lines 32–53):**

```python
league = await self._league_repo.get_by_id(league_id)  # loads all players + teams

player = next(
    (p for p in league.players if p.nickname == normalized_name),
    None,
)

team = next(
    (
        t for t in league.teams
        if t.player_id_1 == player.player_id or t.player_id_2 == player.player_id
    ),
    None,
)
```

**Underlying SQL (`get_by_id` with `selectinload`):**

```sql
SELECT * FROM leagues WHERE league_id = :league_id;
SELECT * FROM players WHERE league_id = :league_id;
SELECT * FROM teams   WHERE league_id = :league_id;
```

The player and team lookups then happen entirely in Python.

---

## Why This Is Not Optimized

### 1. DDD Aggregate Boundary

In this codebase, `Player` and `Team` are **entities owned by the `League` aggregate**.
The `LeagueRepository` is the only sanctioned way to load them — it always fetches the
full aggregate (league + players + teams) as a consistent unit.

A targeted query to resolve a player nickname directly to a `team_id` would require
bypassing the aggregate, for example:

```sql
SELECT t.team_id
FROM players p
JOIN teams t
  ON p.player_id = t.player1_id OR p.player_id = t.player2_id
WHERE p.league_id     = :league_id
  AND p.nickname_normalized = :nickname;
```

This query crosses the aggregate boundary — it reads internal state of the `League`
aggregate without going through the `LeagueRepository`. Introducing it would mean either:

- Adding a cross-aggregate query method to `LeagueRepository`, which breaks its
  single-responsibility as an aggregate loader, or
- Creating a dedicated **read model / query service** outside the domain layer
  (e.g. a `PlayerQueryService`), which is significant architectural overhead for a
  lookup that costs microseconds at current scale.

### 2. Scale Is Not a Concern

Matches accumulate without bound — a league played for years can have thousands of
match rows. That is why match fetching benefits meaningfully from SQL filtering.

Roster size is different. A tennis league roster is bounded in practice:

| Entity   | Realistic upper bound |
|----------|-----------------------|
| Players  | ~50–100 per league    |
| Teams    | ~25–50 per league     |
| Matches  | Unbounded (grows forever) |

Loading 50–100 player rows and 25–50 team rows is a trivially small payload. The
three SQL queries issued by `get_by_id` complete in a single round-trip per table and
transfer at most a few kilobytes. There is no meaningful latency or memory cost to
optimize away.

### 3. The Optimization Would Be Premature

Premature optimization here would:

- Add a new query method or service with its own tests and maintenance burden.
- Complicate the aggregate loading strategy for all use cases that share `get_by_id`.
- Provide zero measurable performance benefit at current or realistic future scale.

---

## When This Decision Should Be Revisited

Revisit this decision if any of the following become true:

- League rosters regularly exceed **500+ players**, making the full roster load
  observably slow (measurable via profiling, not assumption).
- The use case is called in a **high-frequency hot path** (e.g., batch processing or
  real-time feeds) where even small per-call costs compound.
- The architecture already introduces a **read-model layer** for other reasons, at which
  point a dedicated player→team resolution query fits naturally without added complexity.

---

## What Was Optimized Instead

The match fetching step — which *does* grow unboundedly — is covered in:

> `16_sql_optimization_match_history_by_player.md`
