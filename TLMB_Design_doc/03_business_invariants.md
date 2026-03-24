# Business Invariants

## Invariant: League Title Uniqueness

- Statement: Every league must have a title that is unique across the entire system, compared case-insensitively.
- Why it exists: Prevents ambiguity when a host or player references a league by name; ensures the title is a meaningful human-readable identifier.
- Scope / context: League Management
- Likely owner: League aggregate root (enforced on creation and on any future rename)
- Violated when: A new league is created with a title that, when compared case-insensitively, matches an existing league's title.
- Notes: Both league title uniqueness and player nickname uniqueness within a league use case-insensitive comparison. League title uniqueness is system-wide; player nickname uniqueness is scoped per-league.

---

## Invariant: Player Nickname Uniqueness Within a League

- Statement: No two players within the same league may share the same nickname when compared case-insensitively.
- Why it exists: Player identity is determined solely by nickname within a league; duplicate nicknames would make it impossible to resolve which player is meant in a match submission.
- Scope / context: League Management
- Likely owner: League aggregate root (checked on implicit registration and on admin nickname edits)
- Violated when: A new player is registered with a nickname that, when lowercased, matches an existing player's nickname in the same league. Also violated if an admin changes a player's nickname to one already in use by another player in the same league.
- Notes: Case-insensitive comparison is enforced by the backend. Players do not need to use their actual name — any unique nickname within the league is valid.

---

## Invariant: One Team Per Player Per League

- Statement: A player may belong to at most one team within a given league.
- Why it exists: Standings and roster integrity depend on each player having a single, unambiguous team affiliation. A player on two teams would create contradictory match records.
- Scope / context: League Management
- Likely owner: League aggregate root (checked on implicit registration and on admin team reassignment)
- Violated when: A match submission attempts to register a player who is already a member of a different team in the same league. Also violated if an admin reassigns a player to a second team without removing them from the first.
- Notes: This invariant is the primary rejection condition for match submissions. The backend returns a structured error code when it is violated; the AI chatbot renders this as a natural-language explanation to the player.

---

## Invariant: Team Has Exactly Two Distinct Players

- Statement: A team must always consist of exactly two players, and those two players must be distinct (a player cannot be paired with themselves).
- Why it exists: The system models doubles tennis, where every team is a pair. A team with one player or with the same player listed twice is not a valid doubles team.
- Scope / context: League Management
- Likely owner: Team entity inside the League aggregate (enforced at team creation time)
- Violated when: A team is created with fewer or more than two player slots, or when both player slots reference the same player.
- Notes: This invariant is enforced implicitly during implicit registration — the match submission always provides exactly two player nicknames per team, and the backend validates the structure before proceeding.

---

## Invariant: Players and Teams Are Created Only Through Match Submission

- Statement: No player or team record may exist in the league unless it was created as part of a confirmed match submission.
- Why it exists: Explicit pre-registration is out of scope in V1. Allowing orphaned player/team records (not linked to any match) would pollute the roster and create ambiguous state.
- Scope / context: League Management
- Likely owner: League aggregate root (the SubmitMatchResult application use case is the only path through which players/teams are created; it invokes League aggregate methods and saves through LeagueRepository)
- Violated when: A player or team is inserted into the league outside of the match submission flow (e.g. via a direct admin create-player endpoint, if one ever existed).
- Notes: In V1, there is no explicit player or team creation endpoint. The only creation path is implicit registration triggered by a match submission. Admin operations may edit or delete existing records but cannot create new ones outside this flow.

---

## Invariant: Match Involves Two Distinct Teams

- Statement: The two teams in a match (team1 and team2) must be different teams; a team cannot play against itself.
- Why it exists: A match between a team and itself is not a valid doubles result and would corrupt standings calculations.
- Scope / context: Match Recording
- Likely owner: Match aggregate root (enforced on match creation via `team1_id ≠ team2_id` check)
- Violated when: A match submission provides the same team identifier for both team1 and team2.
- Notes: This invariant, combined with the "One Team Per Player Per League" invariant owned by the League aggregate, derivably guarantees that no player can appear on both sides of a match. A separate explicit cross-player check is therefore not needed — if the two team IDs are distinct and each player belongs to exactly one team, player uniqueness across sides is structurally guaranteed.

---

## Invariant: Set Scores Are Non-Negative Integers

- Statement: Each set score in a match result must be a non-negative integer. Negative values and non-integer values are structurally invalid.
- Why it exists: The backend must persist a coherent match record. Malformed score data would corrupt match history and standings computations.
- Scope / context: Match Recording
- Likely owner: SetScore value object (validated on construction)
- Violated when: A match submission contains a set score that is negative, non-numeric, or missing.
- Notes: No tennis-specific scoring rules are enforced in V1 (e.g. no requirement to reach 6 games or win by 2). Any pair of non-negative integers is structurally valid. Stricter score validation may be added in a future version.

---

## Invariant: Team Cannot Be Deleted While Match Records Exist

- Statement: A team record may not be deleted from the league if any match record references that team.
- Why it exists: Deleting a team while matches reference it would leave orphaned match records, corrupt standings, and break match history. The host must explicitly clean up match records before removing the team.
- Scope / context: Admin Operations → League Management / Match Recording
- Likely owner: Application layer (precondition check before delegating to the domain)
- Violated when: A delete-team admin request is made for a team that still has one or more associated match records in the league.
- Notes: This is a hard precondition enforced by the backend, not a cascading auto-delete. The backend returns a structured error if the precondition fails, listing that matches must be removed first. The host uses the delete-match admin action to clear the affected records before retrying the team deletion.

---

## Invariant: Standings Are Derived Solely From Persisted Match Records

- Statement: The standings for a league are always computed on the fly from the current set of persisted match records. There is no cached, pre-computed, or separately stored standings state.
- Why it exists: Any cached standings could diverge from the match record truth if a match is edited or deleted. Computing on the fly guarantees consistency with the underlying data at all times.
- Scope / context: Standings & History (Query Side)
- Likely owner: Standings query / read model (no write aggregate; enforced by design)
- Violated when: A standings value is stored separately and not recomputed after a match is added, edited, or deleted.
- Notes: This is a V1 design constraint, not a rule enforced by a domain aggregate. It should be treated as an architectural invariant: no code path should write a standings record to the database. In a future version with caching or materialised views, this invariant would need a cache-invalidation strategy.

---

## Cross-Aggregate Constraints

### Constraint: Implicit Registration and Match Persistence Are Atomic

- Statement: When a match submission involves new players or a new team, the creation of those player/team records and the creation of the match record must succeed or fail together as a single atomic operation.
- Why it exists: Partial state — players registered but no match saved, or a match saved but players not registered — would leave the league in an inconsistent state. The roster would not match the match history.
- Scope / context: Cross-aggregate: League Management (player/team creation) and Match Recording (match creation)
- Owner: SubmitMatchResult application use case — loads the League aggregate through LeagueRepository, invokes League domain behavior to register any new players/teams, creates the Match aggregate, and persists both through their repositories within a single database transaction
- Violated when: Player/team records are committed to the database without the associated match record, or vice versa.
- Notes: This constraint is enforced at the application layer via a single transaction boundary, not inside either aggregate root individually. The use case is the coordination point. All nickname lookups are scoped to the leagueId from the incoming command — cross-league resolution is impossible by design, since unknown nicknames trigger implicit registration within the target league rather than a global lookup.
