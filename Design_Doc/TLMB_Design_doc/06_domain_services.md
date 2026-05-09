# Domain Services

## Service: StandingsCalculator

- Business purpose: Compute the ranked standings for a league from the full set of persisted match records, using the league's configured **ranking subject** (`"team"` or `"player"`) and **ordered `tie_breakers` list**. Both come from `LeagueRules` v2/v3 — see [17_configurable_ranking.md](17_configurable_ranking.md) and [18_configurable_ranking_v3.md](18_configurable_ranking_v3.md). Applies tied-rank logic — rows whose full metric tuple is equal share the same rank; the next rank after a tie skips positions (standard competition ranking, e.g. two rows at rank 1 means the next row is rank 3).
- Why it is not an aggregate method: Standings computation draws from two separate aggregate boundaries — Match records (for win/loss/games outcomes) and League (for team identity, player display names, and ranking rules). Neither aggregate owns the other's data; placing this logic on either root would force it to receive foreign aggregate state as a parameter, which is a misplacement of responsibility. As a pure, stateless calculation with no side effects, it is correctly modeled as a standalone domain service.
- Inputs:
  - `matches: list[Match]` — all persisted match records for the league (supplies win/loss/games outcomes)
  - `teams: list[Team]` — team entities from the League aggregate (supplies team identity and player ID references)
  - `players: list[Player]` — player entities from the League aggregate (supplies nicknames for display)
  - `rules: LeagueRules` — supplies `ranking_subject` (which row shape to emit) and `tie_breakers` (which metric tuple to sort by)
- Outputs: `list[StandingsEntry]` — discriminated by `subject_kind`. Both variants carry `rank`, `matches_played`, `wins`, `losses`, `games_won`, `games_lost`, `games_diff`, `win_pct`. Team variant additionally carries `team_id`, `player1_nickname`, `player2_nickname`. Player variant additionally carries `player_id`, `nickname`. Sorted ascending by `rank`.
- Purity / no-IO rule: Pure — no DB calls, no HTTP, no side effects; receives all required state as input parameters and returns a computed result.
- Related aggregates: League (for team and player data, plus rules), Match (for win/loss/games records).
- Used for:
  - pure calculation / decision flow (called by the `GetStandingsUseCase` and `GetStandingsByPlayerUseCase` after loading matches through `MatchRepository` and league data through `LeagueRepository`).

---

## Ranking Algorithm Notes

- A row's sort key is `tuple(metric_value(m) for m in rules.tie_breakers)`, sorted **descending**. The first metric is primary; subsequent metrics break ties.
- Allowed metrics (v2/v3): `matches_won`, `match_diff` (= matches_won − matches_lost), `games_won` (sum of subject's per-match `int(team_score)`), `games_lost` (sum of opponent's per-match `int(team_score)`), `games_diff` (= games_won − games_lost), `win_pct` (= matches_won / matches_played, with 0/0 = 0.0).
- "Games" means the integer per-side score already stored on `SetScore` — v2/v3 makes no schema change to matches.
- Standard competition ranking: rows with equal full metric tuples receive the same rank. The next row after a tied group receives rank = (1-indexed position in sorted list), not (previous rank + 1). Dense rank is **not** offered as configuration.
- A win is determined by comparing `team1_score` and `team2_score` on each `SetScore` value object: the side with the higher score wins the match. Equal scores produce a draw — draws contribute zero wins and zero losses but are counted in `matches_played` (see Notes below).
- For `ranking_subject == "player"` (v3 cross-rule: only legal when `one_team_per_player == false`), each match outcome is credited to **both** members of the winning team and **both** members of the losing team. Because OTPP=false allows a player to belong to multiple teams, a player accumulates wins/losses/games across **every** team they appear on, regardless of who their partner was for any given match. When the same matches are recomputed under `(team, OTPP=false)`, each team row only aggregates that specific partnership's matches; the two row shapes therefore convey distinct information. See the worked example in [18_configurable_ranking_v3.md](18_configurable_ranking_v3.md). The same-player-on-both-sides guard inside `_compute_for_players` is defense-in-depth only — the primary defense is `SamePlayerOnBothTeamsError` raised by `SubmitMatchResultUseCase` before any persistence.

### Worked example: tie broken by `games_diff`

Three teams, `tie_breakers = ["matches_won", "games_diff"]`:

| Team | Matches won | Games for | Games against | Games diff |
|---|---|---|---|---|
| A | 2 | 12 | 9 | +3 |
| B | 2 | 10 | 11 | -1 |
| C | 1 | 8 | 10 | -2 |

A and B tie on `matches_won` (both 2). Sort descending by `games_diff` breaks the tie: A gets rank 1, B gets rank 2, C gets rank 3.

---

## Notes / Resolved Decisions

- **Draw handling (resolved):** If both teams score equally in a set, the match contributes zero wins and zero losses to both teams. Draws are structurally valid match records and are counted in `matches_played` (the denominator of `win_pct`) but have no effect on `matches_won` or `matches_lost`.
- **Single set per match (resolved):** V1/V2 use exactly one `SetScore` per match. The win-determination logic compares `team1_score` vs `team2_score` on that single pair. Multi-set support, if needed in a future version, would require updating this logic.
- **Player nickname display:** The service resolves player nicknames at calculation time from the passed `list[Player]`. It does not call any repository. The use case is responsible for loading the match list, the league (with players and teams), and the league's rules before invoking the service.
- **`win_pct` for unplayed subjects:** A subject with `matches_played == 0` produces `win_pct == 0.0` so that sort order remains total. Such subjects always sort below any subject with at least one win.

