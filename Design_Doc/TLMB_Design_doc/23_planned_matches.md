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
3. `LeagueRepository.lock_by_id` locks only the league row before upserts; it does
   not hydrate players, aliases, pairs, or rules. A missing league raises
   `LeagueNotFoundError`. Listing uses the unlocked `exists` query.
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

## Recording and consuming a plan

The existing singles and doubles result commands accept optional
`planned_match_id: UUID | None = None`. Their current participant and score fields
remain required, and their 201 `{match_id, created_at}` responses remain unchanged.
Omitted/null IDs use manual recording without reading or deleting any plan.

For a supplied ID, the existing recording Unit of Work locks the league first,
then reads the scoped plan with `SELECT ... FOR UPDATE`. A missing plan raises
`PlannedMatchNotFoundError` (404). `PlannedMatchValue.validate_participants` checks
the format (422 `InvalidPlannedMatchError`) and normalized names per side (409
`PlannedMatchMismatchError`). Comparison trims/lowercases with `PlayerNickname`;
teammate ordering may differ, side ordering may not. It does not resolve aliases
to substitute different names, and it never changes the saved value.

The same use case then applies normal nickname, score, roster, alias resolution,
pair membership, and rematch rules. It saves the actual result and league activity,
deletes exactly `(league_id, planned_match_id)`, and commits once. The plan repository
shares the existing UoW session. Validation, save, deletion, or commit errors cannot
leave partial result-related changes; a rolled-back transaction retains the plan.

Uploads take the same league-before-plan lock order using the lightweight league
lock. Concurrent recordings of one pending plan produce one result and a 404 for
the later request. No consumption receipt or result-to-plan link is stored: retries
after consumption return 404, and later uploads (including queued uploads) may
recreate the deleted UUID. Preventing recreation is outside this feature.

## Deleting a pending plan

`DELETE /leagues/{league_id}/planned-matches/{planned_match_id}` calls
`DeletePlannedMatchUseCase` and returns 204 with no body after commit. Both path
IDs must be UUIDs. Access is public via the league link, with the existing CORS
configuration and a 60/minute rate limit; no scores or host token are required.

The dedicated `DeletePlannedMatchUnitOfWork` shares one session between the league
and plan repositories. It acquires the lightweight league lock, issues the existing
scoped plan deletion, and commits once. Missing league/plan errors return 404;
storage errors roll back. No roster hydration, participant validation, aggregate
save, recorded result, standings change, or activity-date update is involved.
Deletion by ID also permits cleanup of a malformed saved value.

This follows the same league-before-plan lock order as uploads and recording.
The losing operation in a recording/deletion race gets 404; an already recorded
result is never deleted here. A later upload can recreate the same UUID. No
tombstone, time-window constraint, or migration is introduced. Frontend wiring is
covered by the [deletion guide](../../docs/planned-match-deletion-frontend-guide.md).

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

Recording/consumption uses these existing tables and requires no new migration.

Tests cover pure grammar and nickname invariants, use-case orchestration, HTTP
validation, real PostgreSQL upserts and concurrency, complete rollback on storage
and commit failures, migration upgrade/downgrade, cross-league isolation, legacy
record access, and unchanged domain state across all registration/pair/rematch
settings. Integration/E2E suites must target explicitly isolated databases.
