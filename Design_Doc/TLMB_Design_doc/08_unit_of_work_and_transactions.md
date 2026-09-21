# Unit of Work and Transaction Boundaries

## Transaction Category Overview

```mermaid
flowchart LR
    subgraph UOW ["Requires Unit of Work\n(repositories commit atomically)"]
        SMR["SubmitMatchResult / SubmitSinglesMatchResult\nLeague + Result + optional PlannedMatch"]
    end
    subgraph SINGLE ["Single Repository Write\n(no UoW — inherently atomic)"]
        CL["CreateLeague → LeagueRepo"]
        EPN["EditPlayerNickname → LeagueRepo"]
        DT["DeletePair → LeagueRepo"]
        EMS["EditMatchScore → MatchRepo"]
        DM["DeleteMatch → MatchRepo"]
    end
    subgraph READ ["Read-Only\n(no write transaction)"]
        GS["GetStandings\nLeagueRepo + MatchRepo + StandingsCalculator"]
        GMH["GetMatchHistory\nMatchRepo + nickname resolution"]
        GLR["GetLeagueRoster\nLeagueRepo only"]
    end

    style UOW fill:#f8d7da,stroke:#dc3545
    style SINGLE fill:#d1ecf1,stroke:#17a2b8
    style READ fill:#d4edda,stroke:#28a745
```

---

## Transactional Action: SubmitMatchResult

- Business action: Submit Match Result (including implicit player/pair registration when new players are present)
- Why atomicity is required: The League aggregate save (which persists any newly registered players and pairs) and the Match aggregate save (which persists the new match record) must succeed or fail together. A partial commit — players/pairs registered but no match saved, or a match saved but players not registered — would leave the league roster and match history in an irrecoverably inconsistent state.
- Aggregate(s) involved: League, Match
- Repository interfaces involved: LeagueRepository, MatchRepository
- Unit of Work needed?: Yes
- Unit of Work name: SubmitMatchResultUnitOfWork
- Repositories participating in same transaction: LeagueRepository, MatchRepository
- Commit scope: LeagueRepository.save(league) — persists updated roster with any new players/pairs — and MatchRepository.save(match) — persists the new match record — within a single DB transaction
- Rollback trigger: any domain error (invariant violation, pair conflict), save error, or DB constraint violation; entire transaction is rolled back
- Notes: When all players are already known and the pair already exists, the League save is still issued but results in no-ops (upsert with no changes). The transaction boundary is the same regardless of whether implicit registration occurred.

---

## Optional planned-match consumption

Both existing result Units of Work also expose `PlannedMatchRepository`, using the
same SQLAlchemy session as the league and result repositories. With a non-null
`planned_match_id`, lock the league first, then lock the plan scoped by league/ID.
The plan validates submitted format and names before normal result recording.
After result and league writes, hard-delete the plan and commit once. Any failure
rolls back the result, registrations, activity metadata, and plan deletion together.

Planned uploads acquire a lightweight league-row lock before their batch upserts,
so both workflows lock league then plans. No roster hydration or league save is
needed during uploads. A recording queued behind consumption finds no plan and
returns 404. An upload queued behind consumption can recreate that UUID: no receipt
table or consumed-ID check is maintained. Manual result submissions skip plan reads
and deletion. See [planned matches](23_planned_matches.md).

---

## Transactional Action: DeletePlannedMatch

`DeletePlannedMatchUnitOfWork` locks the league row without roster hydration and
deletes only the scoped pending plan through `PlannedMatchRepository.delete`.
The SQL DELETE acquires the plan-row lock, preserving league-before-plan ordering
with upload and recording. Both repositories share the session; the use case
commits once before 204, and a failure rolls back deletion. This explicit boundary
also keeps the league lock until deletion commits. No league aggregate is saved
and no recorded-result or activity metadata changes occur.

---

## Single-Repository Write Actions (No Unit of Work Required)

### CreateLeague
- Business action: Create League
- Why no Unit of Work is needed: Only one repository is written to (LeagueRepository). A single repository save is inherently atomic.
- Repository written: LeagueRepository
- Notes: hostToken UUID is generated in the use case before calling League.create(); no cross-aggregate persistence involved.

### EditPlayerNickname
- Business action: Edit Player Nickname (Admin)
- Why no Unit of Work is needed: Only LeagueRepository is written to. The nickname update is a single aggregate mutation.
- Repository written: LeagueRepository

### DeletePair
- Business action: Delete Pair (Admin)
- Why no Unit of Work is needed: MatchRepository.has_matches_for_pair is a read-only precondition check; no write occurs on MatchRepository. Only LeagueRepository is written to.
- Repository written: LeagueRepository
- Notes: The read from MatchRepository (precondition check) and the write to LeagueRepository are sequential, not transactional. The precondition must be verified before the domain mutation begins; if the check passes and a concurrent insert creates a match for that pair before the delete commits, the DB foreign key constraint on the matches table acts as the final safety net.

### EditMatchScore
- Business action: Edit Match Score (Admin)
- Why no Unit of Work is needed: Only MatchRepository is written to. Single aggregate mutation.
- Repository written: MatchRepository

### DeleteMatch
- Business action: Delete Match (Admin)
- Why no Unit of Work is needed: Only MatchRepository is written to (hard delete). No other aggregate state changes.
- Repository written: MatchRepository

---

## Read-Only / Calculation Actions (No Write Transaction Required)

### GetStandings
- Business action: View Standings
- Why no write transaction is needed: Pure read — loads existing match and league data, computes standings in memory, returns a projection. No state is mutated.
- Aggregate(s) or read inputs loaded: all Match records for the league (via MatchRepository), League aggregate with Players and Pairs (via LeagueRepository)
- Repository / query interfaces involved: MatchRepository.get_all_by_league, LeagueRepository.get_by_id
- Domain service used?: Yes — StandingsCalculator receives the loaded match list, pair list, and player list and returns a ranked list of StandingsEntry
- Notes: Both repository calls are read-only. They may be executed in a single read transaction or independently; no write lock is needed.

### GetMatchHistory
- Business action: View Match History
- Why no write transaction is needed: Read-only projection of match records ordered chronologically.
- Aggregate(s) or read inputs loaded: all Match records for the league
- Repository / query interfaces involved: MatchRepository.get_all_by_league
- Domain service used?: No
- Notes: Returns a chronological list; no domain computation required beyond loading and ordering by created_at (infrastructure-managed DB column).

### GetLeagueRoster
- Business action: View League Roster
- Why no write transaction is needed: Read-only projection of the current league player and pair roster.
- Aggregate(s) or read inputs loaded: League aggregate with Players and Pairs
- Repository / query interfaces involved: LeagueRepository.get_by_id
- Domain service used?: No
- Notes: Returns the player list and pair list as-is from the loaded League aggregate.
