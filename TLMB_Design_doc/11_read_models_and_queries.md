# Read Models and Queries

## Read Model: StandingsView

- Used by: Player (via leagueId) or League Host (via hostToken) viewing the current standings table
- Backed by: Computed on the fly from all Match records in the league + Team and Player data from the League aggregate; no materialized table in V1
- Freshness requirement: Real-time — computed at request time from current persisted match records; reflects any edits or deletions immediately
- Strongly consistent or eventual: Strongly consistent — computed directly from the write-side data in the same DB read
- Fields exposed:
  - rank (int — shared rank for tied teams)
  - team_id (str)
  - player1_nickname (str)
  - player2_nickname (str)
  - wins (int)
  - losses (int)
- Why this is NOT a write aggregate: Standings are a derived projection of match records. No standings value is ever stored or mutated independently. Enforced as an architectural invariant in V1: no code path writes a standings record to the database.

---

## Read Model: MatchHistoryRecord

- Used by: Player (via leagueId) or League Host (via hostToken) viewing the chronological list of match results
- Backed by: All Match records for the league, with team_id references resolved to player nicknames from the League aggregate at read time
- Freshness requirement: Real-time — reflects the current persisted match records and current player nicknames
- Strongly consistent or eventual: Strongly consistent
- Fields exposed:
  - match_id (str)
  - team1_player1_nickname (str)
  - team1_player2_nickname (str)
  - team2_player1_nickname (str)
  - team2_player2_nickname (str)
  - team1_score (str)
  - team2_score (str)
  - created_at (datetime, UTC — infrastructure-managed DB insert timestamp; used in place of a domain recorded_at field in V1)
- Why this is NOT a write aggregate: Match history is a read-only projection. Matches are only created or mutated through the Match aggregate root. No MatchHistoryRecord is ever persisted as a separate entity.
- Notes: Nickname resolution happens at read time from the current League state. Admin nickname edits retroactively affect how historical matches are displayed — this is an accepted trade-off in V1.

---

## Read Model: RosterView

- Used by: Player (via leagueId) or League Host (via hostToken) viewing the current list of players and teams in a league
- Backed by: Player and Team entities from the League aggregate
- Freshness requirement: Real-time — reflects the current League state including any admin edits or deletions
- Strongly consistent or eventual: Strongly consistent
- Fields exposed (players): player_id (str), nickname (str)
- Fields exposed (teams): team_id (str), player1_nickname (str), player2_nickname (str)
- Why this is NOT a write aggregate: The roster is a direct projection of League aggregate state. Players and teams are only created or mutated through the League aggregate root.

---

## Query: GetStandings

- Inputs: league_id (str)
- Auth: leagueId possession (player-level access) or hostToken (admin access) — both accepted
- Filters: scoped to the given league_id
- Sorting / pagination: results sorted ascending by rank; no pagination (leagues are small in V1)
- Output: list[StandingsView] ordered by rank ascending
- Domain service used?: Yes — StandingsCalculator receives the loaded match list, team list, and player list
- Notes: Both LeagueRepository.get_by_id and MatchRepository.get_all_by_league are called; no write lock needed

---

## Query: GetMatchHistory

- Inputs: league_id (str)
- Auth: leagueId possession (player-level access) or hostToken (admin access) — both accepted
- Filters: scoped to the given league_id
- Sorting / pagination: sorted by created_at descending; no pagination in V1
- Output: list[MatchHistoryRecord] ordered by created_at descending
- Domain service used?: No
- Notes: Match records are loaded via MatchRepository.get_all_by_league; team-to-nickname resolution uses the League aggregate loaded via LeagueRepository.get_by_id

---

## Query: GetMatchHistoryByPlayer

- Inputs: league_id (str), player_name (str — normalized to lowercase)
- Auth: leagueId possession (player-level access) — possession is sufficient
- Filters: scoped to the given league_id; further filtered to matches involving the resolved player's team
- Sorting / pagination: sorted by created_at descending; no pagination in V1
- Output: list[MatchHistoryRecord] ordered by created_at descending (empty list if player has no current team)
- Domain service used?: No
- Notes: Player is resolved by normalized nickname from the League aggregate. Team is identified from league.teams. Matches are loaded via MatchRepository.get_all_by_league and filtered in-memory. Nickname resolution uses current League state — same retroactive-edit behaviour as GetMatchHistory.

---

## Query: GetLeagueRoster

- Inputs: league_id (str)
- Auth: leagueId possession (player-level access) or hostToken (admin access) — both accepted
- Filters: scoped to the given league_id
- Sorting / pagination: players sorted alphabetically by nickname; teams sorted by player1_nickname alphabetically; no pagination in V1
- Output: RosterView (players: list[PlayerEntry], teams: list[TeamEntry])
- Domain service used?: No
- Notes: Loaded directly from the League aggregate via LeagueRepository.get_by_id; no secondary repository call needed

