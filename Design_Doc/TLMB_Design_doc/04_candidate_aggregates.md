# Candidate Aggregates

## Aggregate Boundary Overview

```mermaid
flowchart TD
    subgraph LEAGUE ["League Aggregate  (consistency boundary)"]
        LR["League Root"]
        P["Player entities\n(nickname · playerId)"]
        T["Pair entities\n(playerId_1 · playerId_2)"]
        LR --> P
        LR --> T
    end

    subgraph MATCH ["Match Aggregate  (consistency boundary)"]
        MR["Match Root"]
        SS["SetScore value object\n(pair1_score · pair2_score)"]
        MR --> SS
    end

    subgraph SINGLES ["SinglesMatch Aggregate  (consistency boundary)"]
        SMR["SinglesMatch Root"]
        SSS["SetScore value object\n(player1_score · player2_score)"]
        SMR --> SSS
    end

    subgraph QUERY ["Query Side  (no aggregate — derived read models)"]
        ST["Standings\n(computed on the fly)"]
        MH["Match History"]
        RV["Roster View"]
    end

    MATCH -->|"references by pair1_id, pair2_id\n(opaque IDs — no structural dependency)"| LEAGUE
    SINGLES -->|"references by player1_id, player2_id\n(opaque IDs — no structural dependency)"| LEAGUE
    LEAGUE -.->|"pair & player data\nfor display"| QUERY
    MATCH -.->|"match records\nfor projection"| QUERY
    SINGLES -.->|"singles records\nfor projection"| QUERY

    style QUERY fill:#f8f9fa,stroke:#6c757d,stroke-dasharray: 5 5
```

---

## Aggregate: League

- Aggregate root: League
- Main responsibility: Own the full lifecycle of a league — its identity and access credentials, its roster of players, and the pair compositions formed by those players. Enforce all membership and roster invariants.
- Invariants owned:
  - League title uniqueness (system-wide, case-insensitive)
  - Player nickname uniqueness within a league (case-insensitive)
  - One pair per player per league (a player may belong to at most one pair)
  - Pair has exactly two distinct players
  - Players and pairs are created only through match submission (no standalone creation endpoint)
- State changed atomically: league title, player roster (add / edit nickname), pair roster (create / delete), player-to-pair membership
- References to other aggregates by: none (owns all roster state internally; Match references Pair by ID from the outside)
- Why this should be one aggregate: The three roster invariants (nickname uniqueness, one-pair-per-player, two-distinct-players-per-pair) are tightly coupled — all three must be checked together whenever a player or pair is added or modified. Splitting players and pairs into separate aggregates would force cross-aggregate transactions for every implicit registration.
- Why this should NOT absorb neighboring concepts: Match result records belong to Match Recording, not League. Pulling match data into this aggregate would bloat it with write concerns unrelated to roster management and make the capacity for large leagues unmanageable.
- Open questions:
  - For very large leagues (hundreds of pairs), loading all players and pairs into memory on every match submission could become expensive. For V1 with small recreational groups, this is acceptable. Revisit if league sizes grow significantly.
- Resolved decisions:
  - hostToken is stored as plaintext. No hashing required; security concern is not a priority for this system.

---

## Aggregate: Match

- Aggregate root: Match
- Main responsibility: Own a single confirmed doubles match result — the two opposing pair references, the set scores, and the match-level structural invariants.
- Invariants owned:
  - Match involves two distinct pairs (pair1_id ≠ pair2_id)
  - Set scores are non-negative integers
- State changed atomically: set scores (on admin edit), match record existence (on admin delete)
- References to other aggregates by: pair1_id and pair2_id (opaque references to Pair entities inside the League aggregate; the Match does not hold player lists directly after creation)
- Why this should be one aggregate: A match result is a single consistent unit — its two pair slots and set scores must be stored together; partial saves produce nonsensical records. Admin score edits apply to the whole match at once.
- Why this should NOT absorb neighboring concepts: Player and pair identity belong to League. Standings computation is a read-side projection, not a write-side concern of Match. Pulling those into Match would entangle its consistency boundary with roster management.
- Resolved decisions:
  - Match stores pair IDs only. Player nicknames are always resolved on read from the current League state. Admin nickname edits will retroactively affect historical display — this is acceptable.
  - Deleted matches are hard-deleted. No soft-delete / archive required.

---

## Aggregate: SinglesMatch

- Aggregate root: SinglesMatch
- Main responsibility: Own a single confirmed singles match result — the
  two opposing player references, the set scores, and the match-level
  structural invariants.
- Invariants owned:
  - Match involves two distinct players (`player1_id != player2_id`)
  - Set scores are non-negative integers
- State changed atomically: set scores (on player/admin edit), match
  record existence (on player/admin delete)
- References to other aggregates by: `player1_id` and `player2_id`
  (opaque references to `Player` entities inside the League aggregate)
- Why this should be one aggregate: a singles result is a single
  consistent unit, parallel to doubles `Match`, but it cannot reuse
  `Pair` because a pair is always exactly two players.
- Resolved decisions:
  - Singles matches store player IDs directly; no degenerate one-player
    pair is created.
  - Deleted singles matches are hard-deleted. Deletion recomputes
    `leagues.latest_match_date_single` from remaining singles rows.

---

## Aggregate: (None — Query Side Only)

- Standings, match history, and roster views are **not aggregates**. They are read models derived on the fly from League, Match, and SinglesMatch state.
- There is no Standings aggregate root. No standings record is persisted or mutated.
- Admin Operations is not a separate aggregate; it is a set of admin-only application commands that operate on the League and Match aggregates through a separate router with hostToken authorization.

---

## Decision Questions Answered

| Question | Answer |
|---|---|
| What must change together in one transaction? | On match submission: implicit player/pair registration (League) + match record creation (Match) — the SubmitMatchResult use case loads both aggregates through their repositories, invokes their domain behavior, and saves both in one transaction |
| What can be eventually consistent? | Standings reads (always computed on the fly; no write-side consistency concern) |
| What is the external entry point? | League root for all roster mutations; Match root for all result mutations |
| Which child objects should not be edited independently? | Player and Pair entities inside League; SetScore value objects inside Match |
