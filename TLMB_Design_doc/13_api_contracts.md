# API Contracts

## Auth Model

- **Player-facing endpoints:** `league_id` in the URL path is the only access check. Possession of a valid `league_id` is sufficient proof of league membership.
- **Admin endpoints:** Both `league_id` (URL path) and `X-Host-Token` HTTP header are required. The use case loads the League by `league_id` and verifies the token matches that league's stored `host_token`. Returns 401 if the header is missing or the token does not match the league.
- **League creation:** Public — no credentials required; `league_id` and `host_token` are returned in the response.

## Endpoint Overview

```mermaid
flowchart LR
    subgraph player [Player-facing]
        P1["POST /leagues"]
        P2["POST /leagues/{league_id}/matches"]
        P3["GET /leagues/{league_id}/standings"]
        P4["GET /leagues/{league_id}/matches"]
        P5["GET /leagues/{league_id}/roster"]
    end
    subgraph admin ["Admin — league_id + X-Host-Token header"]
        A1["PATCH /admin/leagues/{league_id}/players/{player_id}"]
        A2["DELETE /admin/leagues/{league_id}/teams/{team_id}"]
        A3["PATCH /admin/leagues/{league_id}/matches/{match_id}"]
        A4["DELETE /admin/leagues/{league_id}/matches/{match_id}"]
    end
```

## Error Code → HTTP Status Mapping

| Domain Error | HTTP Status |
|---|---|
| LeagueNotFoundError | 404 |
| PlayerNotFoundError | 404 |
| TeamNotFoundError | 404 |
| MatchNotFoundError | 404 |
| UnauthorizedError (hostToken mismatch or missing) | 401 |
| LeagueTitleAlreadyExistsError | 409 |
| TeamConflictError | 409 |
| NicknameAlreadyInUseError | 409 |
| TeamHasMatchesError | 409 |
| SameTeamOnBothSidesError | 409 |
| SamePlayerWithinSingleTeamError | 422 |
| SamePlayerOnBothTeamsError | 422 |
| InvalidSetScoreError | 422 |

---

## Endpoint: Create League

- Method: POST
- Path: `/leagues`
- Purpose: Create a new league and receive access credentials
- Request shape: `{ "title": "str", "description": "str | null" }`
- Response shape: `{ "league_id": "uuid", "host_token": "uuid" }`
- Use case called: CreateLeagueUseCase
- Error responses: 409 LeagueTitleAlreadyExistsError, 422 validation (blank title)
- Auth notes: Public — no credentials required

---

## Endpoint: Submit Match Result

- Method: POST
- Path: `/leagues/{league_id}/matches`
- Purpose: Record a confirmed doubles match result; implicitly registers any new players and teams
- Request shape:
  ```json
  {
    "team1_nicknames": ["str", "str"],
    "team2_nicknames": ["str", "str"],
    "team1_score": "str",
    "team2_score": "str"
  }
  ```
- Response shape: `{ "match_id": "uuid" }`
- Use case called: SubmitMatchResultUseCase
- Error responses:
  - 404 LeagueNotFoundError
  - 422 SamePlayerWithinSingleTeamError (same player listed twice on one team)
  - 422 SamePlayerOnBothTeamsError (same player appears on both teams)
  - 422 InvalidSetScoreError (non-integer or negative score)
  - 409 TeamConflictError (a player is already on a different team in this league)
  - 409 SameTeamOnBothSidesError (both teams resolve to the same existing team)
- Auth notes: `league_id` in URL path — possession is sufficient

---

## Endpoint: Get Standings

- Method: GET
- Path: `/leagues/{league_id}/standings`
- Purpose: Get the current win/loss standings for all teams in the league
- Request shape: —
- Response shape:
  ```json
  {
    "standings": [
      {
        "rank": 1,
        "team_id": "uuid",
        "player1_nickname": "str",
        "player2_nickname": "str",
        "wins": 3,
        "losses": 1
      }
    ]
  }
  ```
- Use case called: GetStandingsUseCase
- Error responses: 404 LeagueNotFoundError
- Auth notes: `league_id` in URL path — possession is sufficient

---

## Endpoint: Get Match History

- Method: GET
- Path: `/leagues/{league_id}/matches`
- Purpose: Get the chronological list of all recorded match results in the league
- Request shape: —
- Response shape:
  ```json
  {
    "matches": [
      {
        "match_id": "uuid",
        "team1_player1_nickname": "str",
        "team1_player2_nickname": "str",
        "team2_player1_nickname": "str",
        "team2_player2_nickname": "str",
        "team1_score": "str",
        "team2_score": "str",
        "created_at": "ISO 8601 datetime (UTC)"
      }
    ]
  }
  ```
- Use case called: GetMatchHistoryUseCase
- Error responses: 404 LeagueNotFoundError
- Auth notes: `league_id` in URL path — possession is sufficient
- Notes: Sorted by `created_at` descending (most recent first). Player nicknames reflect current state — admin nickname edits retroactively affect display.

---

## Endpoint: Get League Roster

- Method: GET
- Path: `/leagues/{league_id}/roster`
- Purpose: Get the list of all registered players and teams in the league
- Request shape: —
- Response shape:
  ```json
  {
    "players": [
      { "player_id": "uuid", "nickname": "str" }
    ],
    "teams": [
      { "team_id": "uuid", "player1_nickname": "str", "player2_nickname": "str" }
    ]
  }
  ```
- Use case called: GetLeagueRosterUseCase
- Error responses: 404 LeagueNotFoundError
- Auth notes: `league_id` in URL path — possession is sufficient

---

## Endpoint: Edit Player Nickname (Admin)

- Method: PATCH
- Path: `/admin/leagues/{league_id}/players/{player_id}`
- Purpose: Correct or update a player's nickname within a league
- Request shape: `{ "new_nickname": "str" }`
- Response shape: `{ "player_id": "uuid", "new_nickname": "str" }`
- Use case called: EditPlayerNicknameUseCase
- Error responses:
  - 404 LeagueNotFoundError
  - 404 PlayerNotFoundError
  - 401 UnauthorizedError (missing or mismatched X-Host-Token)
  - 409 NicknameAlreadyInUseError
  - 422 validation (blank nickname)
- Auth notes: `league_id` (URL path) + `X-Host-Token` header must both be present and the token must match the league's `host_token`

---

## Endpoint: Delete Team (Admin)

- Method: DELETE
- Path: `/admin/leagues/{league_id}/teams/{team_id}`
- Purpose: Permanently remove a team from the league roster; only allowed when the team has no associated match records
- Request shape: —
- Response shape: 204 No Content
- Use case called: DeleteTeamUseCase
- Error responses:
  - 404 LeagueNotFoundError
  - 404 TeamNotFoundError
  - 401 UnauthorizedError
  - 409 TeamHasMatchesError (associated match records must be deleted first)
- Auth notes: `league_id` (URL path) + `X-Host-Token` header

---

## Endpoint: Edit Match Score (Admin)

- Method: PATCH
- Path: `/admin/leagues/{league_id}/matches/{match_id}`
- Purpose: Correct the set score of a previously recorded match
- Request shape: `{ "team1_score": "str", "team2_score": "str" }`
- Response shape: `{ "match_id": "uuid", "team1_score": "str", "team2_score": "str" }`
- Use case called: EditMatchScoreUseCase
- Error responses:
  - 404 LeagueNotFoundError
  - 404 MatchNotFoundError
  - 401 UnauthorizedError
  - 422 InvalidSetScoreError
- Auth notes: `league_id` (URL path) + `X-Host-Token` header

---

## Endpoint: Delete Match (Admin)

- Method: DELETE
- Path: `/admin/leagues/{league_id}/matches/{match_id}`
- Purpose: Permanently remove a match record from the league
- Request shape: —
- Response shape: 204 No Content
- Use case called: DeleteMatchUseCase
- Error responses:
  - 404 LeagueNotFoundError
  - 404 MatchNotFoundError
  - 401 UnauthorizedError
- Auth notes: `league_id` (URL path) + `X-Host-Token` header
