# Aggregate Design: Match

## Aggregate Root

- Name: Match
- Purpose: Own a single confirmed doubles match result — the two opposing team references, the set score, and all match-level structural invariants.
- Identity field: matchId (UUID)

---

## Invariants Enforced by Root

- Match involves two distinct teams: team1_id and team2_id must differ (enforced on `create`)
- Set score is structurally valid: team1_score and team2_score must both parse as non-negative integers (enforced on `create` and `edit_score`)
- Note: The "no player on both sides" property is not an explicit invariant of this aggregate. It is derivable from "One Team Per Player Per League" (enforced by League) + the two-distinct-teams check above. The Match aggregate does not hold or inspect player lists.

---

## Public Behaviors on Root

### `create(team1_id: UUID, team2_id: UUID, set_score: SetScore) -> Match`

- Purpose: Record a confirmed doubles match result for the league.
- Inputs: team1_id, team2_id (opaque references to Team entities inside the League aggregate), set_score (a SetScore value object already validated on construction)
- State changes: sets matchId (new UUID), leagueId (set from context at construction — passed as an aggregate-level field, not a behavior parameter), team1_id, team2_id, set_score; no explicit recorded_at field on the domain aggregate — match creation time is tracked by the infrastructure-managed created_at column (see Design Decision appendix)
- Invariants checked:
  - team1_id ≠ team2_id (raises error if equal)
  - set_score validity (validated inside SetScore value object construction before this method is called)
- Returns: the newly created Match aggregate instance

### `edit_score(new_set_score: SetScore) -> None`

- Purpose: Allow the host (admin) to correct an erroneously recorded set score.
- Inputs: new_set_score (a SetScore value object)
- State changes: replaces the existing set_score with new_set_score
- Invariants checked: new_set_score validity (validated inside SetScore value object construction before this method is called)
- Notes: Team references are not changed by this operation. Only the score is updated.

---

## Internal Entities

- None. The Match aggregate root holds only value objects and opaque external ID references. There are no child entities with their own identity lifecycle inside Match.

---

## Value Objects

### Value Object: MatchId

- Fields: value (UUID)
- Why not a primitive: semantically distinct from LeagueId and TeamId; prevents accidental cross-type assignment
- Validation / normalization: must be a valid UUID; generated on aggregate creation
- Immutability notes: immutable after creation

### Value Object: SetScore

- Fields: team1_score (string), team2_score (string)
- Why not a primitive: encapsulates the structural validation rule (both fields must parse as non-negative integers); ensures no raw unvalidated score reaches the aggregate
- Validation / normalization: on construction, both team1_score and team2_score must be non-empty strings that parse as integers ≥ 0; invalid input raises a domain error
- Immutability notes: immutable once constructed; `edit_score` replaces the entire SetScore value object on the root

---

## Policies

- None. Match structural validation is simple and handled directly in the aggregate root and SetScore value object construction. No separate policy object is needed.

---

## Domain Events (optional)

"Optional" means: the backend is fully correct without an event bus. These events do not need to be raised, collected, or dispatched for the system to function in V1. No use case depends on them for its primary outcome.

They become necessary only when a consumer concern exists — for example: an audit log, a standings cache, a webhook, or a notification. If no such concern exists yet, AI agents should define the event data classes in `domain/events.py` (so the model is complete and the payloads are documented) but should NOT wire an event bus, create handler classes, or add `pull_domain_events()` calls in use cases until a real consumer is introduced.

**Decision rule for AI agents:**
- No consumer concern identified → define event classes only; skip bus wiring
- Consumer concern identified → define event classes + implement handler + wire in `dependencies.py`

| Event | Emitted by | Payload |
|---|---|---|
| MatchRecorded | `Match.create` | matchId, leagueId, team1_id, team2_id, set_score |
| MatchScoreEdited | `Match.edit_score` | matchId, leagueId, old_set_score, new_set_score |
| MatchDeleted | hard-delete via repository | matchId, leagueId |

---

## External References

- leagueId: stored on the aggregate root; identifies which league this match belongs to (reference into the League aggregate boundary)
- team1_id, team2_id: opaque references to Team entities inside the League aggregate; Match does not hold player lists or nicknames directly

**League rules:** Whether two teams may play more than once in a league is governed by `LeagueRules` on the League aggregate and enforced in `SubmitMatchResultUseCase` (not in this aggregate). See [16_league_rules_and_match_policies.md](../16_league_rules_and_match_policies.md).

---

- Match stores team IDs only. Player nicknames are resolved at read time from the current League state. Admin nickname edits will retroactively affect how historical matches are displayed — this is an accepted trade-off in V1.
- Matches are hard-deleted. No soft-delete or archive mechanism is provided in V1.
- One set per match in V1. SetScore holds a single team1_score / team2_score pair. If multi-set support is needed in a future version, SetScore would need to become a list of score pairs, or a separate SetResult entity would be introduced.

---

## Design Decision: created_at used instead of recorded_at

**Decision (V1):** The Match aggregate does not carry an explicit `recorded_at` domain field. Match creation time is instead provided by an infrastructure-managed `created_at` column (set automatically by the DB on row insert). All business logic that requires the match timestamp — currently only chronological ordering in the match history view — uses `created_at`.

**Rationale:** For V1, a match is always submitted and persisted in the same instant. There is no scenario where the "business moment the match was recorded" would differ from the "DB row insertion time". Adding `recorded_at` as a domain field would duplicate information that the infrastructure already provides reliably, with no practical benefit for V1.

**When to re-introduce `recorded_at` as an explicit domain field:**
- If an admin back-fill feature is added (host submits a match result that occurred in the past, with an explicit match date)
- If match scheduling is introduced (a match is pre-scheduled and later confirmed with its scheduled date as the official result date)
- If auditing or legal compliance requires the business timestamp to be independent of DB insert time
- If the display date in match history ever needs to show a different value than the DB creation timestamp

**Migration path when re-introducing:** Add `recorded_at` as a nullable column first, back-fill it from `created_at` for all existing rows, then make it non-nullable. Update `Match.create()` to accept and store it as a domain field. Update `GetMatchHistoryUseCase` and `MatchHistoryRecord` to use `recorded_at` instead of `created_at`.

