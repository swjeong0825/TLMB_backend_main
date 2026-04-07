# SQL Optimization: `GetMatchHistoryByPlayerUseCase` — Match Fetching

## Problem

The current implementation fetches **all matches in the league** from the database, then
filters in Python to keep only the ones involving the player's team.

**Current flow (`get_match_history_by_player_use_case.py`, lines 56–60):**

```python
all_matches = await self._match_repo.get_all_by_league(league_id)
player_matches = [
    m for m in all_matches
    if m.team1_id == team.team_id or m.team2_id == team.team_id
]
```

**Underlying SQL (`get_all_by_league`):**

```sql
SELECT * FROM matches
WHERE league_id = :league_id
ORDER BY created_at DESC;
```

This pulls every match row in the league across the network into Python memory, regardless
of relevance. As the league accumulates matches over time, this query grows unboundedly
expensive.

---

## Proposed Fix

Three files need to change.

### 1. Domain repository interface

**`app/domain/aggregates/match/repository.py`** — add a new abstract method:

```python
@abstractmethod
async def get_all_by_team(self, team_id: TeamId, league_id: LeagueId) -> list[Match]: ...
```

### 2. SQLAlchemy repository implementation

**`app/infrastructure/persistence/repositories/match_repository.py`** — implement the method.
The `OR` pattern already exists in `has_matches_for_team`; this reuses it with full row
retrieval and ordering:

```python
async def get_all_by_team(self, team_id: TeamId, league_id: LeagueId) -> list[Match]:
    result = await self._session.execute(
        select(MatchORM)
        .where(
            MatchORM.league_id == league_id.value,
            (MatchORM.team1_id == team_id.value) | (MatchORM.team2_id == team_id.value),
        )
        .order_by(MatchORM.created_at.desc())
    )
    return [match_to_domain(row) for row in result.scalars().all()]
```

**Resulting SQL:**

```sql
SELECT * FROM matches
WHERE league_id = :league_id
  AND (team1_id = :team_id OR team2_id = :team_id)
ORDER BY created_at DESC;
```

### 3. Use case

**`app/application/use_cases/get_match_history_by_player_use_case.py`** — replace the
two-step fetch-then-filter with a single optimized call:

```python
# Before
all_matches = await self._match_repo.get_all_by_league(league_id)
player_matches = [
    m for m in all_matches
    if m.team1_id == team.team_id or m.team2_id == team.team_id
]

# After
player_matches = await self._match_repo.get_all_by_team(team.team_id, league_id)
```

The `records.sort(...)` at the end of the method can also be removed since the SQL query
already guarantees `created_at DESC` ordering.

---

## What Is Not Optimized

The league roster load (`league_repo.get_by_id` with `selectinload` for players and teams)
is still needed to resolve the player nickname → `team_id` lookup. This is intentionally
left as-is for two reasons:

1. **DDD aggregate boundary** — Players and teams belong to the `League` aggregate. A
   targeted SQL join bypassing the aggregate would require a separate read-model or query
   service, adding significant architectural complexity.
2. **Scale** — League rosters in a tennis context are small (tens of rows). Loading the
   full roster is a negligible payload and unlikely to ever be a bottleneck.

---

## Test Updates Required

Unit test mocks in `tests/application/test_get_match_history_by_player_use_case.py` must
be updated to stub the new method instead of the old one:

```python
# Before
mock_match_repo.get_all_by_league.return_value = [...]

# After
mock_match_repo.get_all_by_team.return_value = [...]
```

The integration and E2E tests do not need changes — they exercise the full stack and are
unaffected by the internal repository method name.
