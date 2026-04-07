# Domain Services

## Service: StandingsCalculator

- Business purpose: Compute the ranked win/loss standings for all teams in a league from the full set of persisted match records. Applies tied-rank logic — teams with the same win count share the same rank; the next rank after a tie skips positions (standard competition ranking, e.g. two teams at rank 1 means the next team is rank 3). No tiebreaker is applied in V1.
- Why it is not an aggregate method: Standings computation draws from two separate aggregate boundaries — Match records (for win/loss outcomes) and League (for team identity and player display names). Neither aggregate owns the other's data; placing this logic on either root would force it to receive foreign aggregate state as a parameter, which is a misplacement of responsibility. As a pure, stateless calculation with no side effects, it is correctly modeled as a standalone domain service.
- Inputs:
  - `matches: list[Match]` — all persisted match records for the league (supplies win/loss outcomes)
  - `teams: list[Team]` — team entities from the League aggregate (supplies team identity and player ID references)
  - `players: list[Player]` — player entities from the League aggregate (supplies nicknames for display)
- Outputs: `list[StandingsEntry]` — each entry contains:
  - `team_id`
  - `player1_nickname` (resolved from Player list)
  - `player2_nickname` (resolved from Player list)
  - `wins` (count of matches where this team won)
  - `losses` (count of matches where this team lost)
  - `rank` (integer; tied teams share the same rank value)
  - Sorted ascending by rank
- Purity / no-IO rule: Pure — no DB calls, no HTTP, no side effects; receives all required state as input parameters and returns a computed result
- Related aggregates: League (for team and player data), Match (for win/loss records)
- Used for:
  - pure calculation / decision flow (called by the `GetStandingsUseCase` after loading matches through `MatchRepository` and league data through `LeagueRepository`)

---

## Ranking Algorithm Notes

- A team's score is its win count. Losses do not affect rank in V1; rank is purely win-count-based.
- A win is determined by comparing `team1_score` and `team2_score` on each `SetScore` value object: the team with the higher score in the set wins the match. If scores are equal, the match is recorded as a draw — draws are not counted as wins or losses in V1 (see Notes below).
- Teams are sorted descending by wins. Teams with equal win counts receive the same rank. The next team after a tied group receives rank = (position in sorted list), not (previous rank + 1).

---

## Notes / Resolved Decisions

- **Draw handling in V1 (resolved):** If both teams score equally in a set, the match contributes zero wins and zero losses to both teams. Draws are structurally valid match records but have no effect on standings rank.
- **Single set per match in V1 (resolved):** V1 uses exactly one `SetScore` per match. The win-determination logic compares `team1_score` vs `team2_score` on that single pair. Multi-set support, if needed in a future version, would require updating this logic.
- **Player nickname display:** The service resolves player nicknames at calculation time from the passed `list[Player]`. It does not call any repository. The use case is responsible for loading both the match list and the league (with players and teams) before invoking the service.

