# Planned matches

A planned match is an independent aggregate identified by `(league_id, id)`.
It contains a `PlannedMatchValue`: a proposed singles or doubles matchup without
scores. Its only invariant is the lightweight text grammar described in
[API contracts](13_api_contracts.md). It is not a recorded `Match` or `SinglesMatch`.

## Data flow and boundaries

1. The public planned-match router validates UUIDs, request shape, batch uniqueness,
   and value grammar with Pydantic schemas backed by the pure domain validator.
2. `UploadPlannedMatchesUseCase` validates the whole batch and constructs aggregate
   instances before opening its dedicated `UploadPlannedMatchesUnitOfWork`.
3. `LeagueRepository.exists` checks only the league row; it does not hydrate players,
   aliases, pairs, or rules. A missing league raises `LeagueNotFoundError`.
4. The planned-match repository upserts all records using the Unit of Work's shared
   session. The use case commits before producing its response; any exception
   rolls back and closes the session. Repositories never own commits.
5. `GetPlannedMatchesUseCase` checks league existence, reads plans ordered by UUID,
   and returns plain application DTOs containing only `id` and `value`.

Unknown names, repeated names, and repeated matchups are permitted. Neither use
case loads or saves the `League` aggregate, resolves participant identities, calls
registration methods, creates recorded matches, nor recalculates standings.
Current league registration/pair/rematch settings have no effect on planning.
No domain events or external integrations are needed for this version.

## Nicknames and legacy data

The shared pure nickname validator uses the explicit ECMAScript whitespace set.
`PlannedMatchValue` invokes it without trimming and preserves the complete string.
`PlayerNickname` trims and lowercases new names after validation. API request
schemas reuse the same validator, and aggregate methods enforce it for callers
that bypass HTTP. Both match-submission use cases validate before comparisons.

Persisted nicknames use an explicit `from_persisted` constructor. It bypasses new
input restrictions and retains stored bytes. Read queries and alias removal use
lookup candidates that preserve legacy names and the differences between Python
and JavaScript trimming. These paths cannot introduce a new nickname. Canonical
renaming is identified by player ID and validates only the replacement name.
There is no player data migration or database nickname constraint.

## Persistence and delivery

Apply Alembic `015` after `014`; it adds only the three-column `planned_matches`
table described in [persistence strategy](12_persistence_strategy.md). Downgrade
drops this table and its plans, leaving league/player/match data unchanged.
Apply the migration before running the new backend version. Deployment and
frontend upload/UI integration are separate work.

Tests cover pure grammar and nickname invariants, use-case orchestration, HTTP
validation, real PostgreSQL upserts and concurrency, complete rollback on storage
and commit failures, migration upgrade/downgrade, cross-league isolation, legacy
record access, and unchanged domain state across all registration/pair/rematch
settings. Integration/E2E suites must target explicitly isolated databases.
