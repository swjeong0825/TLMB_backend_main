# TLM Backend

Domain logic, PostgreSQL persistence, and REST API for the **Tennis League Manager (TLM)** — a lightweight system that lets a recreational doubles tennis group run a league with no login system and no manual registration.

**Live service:** [https://tlmb.swjapps.com](https://tlmb.swjapps.com)

## Related Projects

| Project | Role |
|---|---|
| **[TLMB_chat_to_intent](https://github.com/swjeong0825/TLMB_chat_to_intent)** | LLM-powered intermediary. Classifies natural-language chat messages into backend intents and returns pre-filled form payloads for write operations. Reads from this backend via `GET` only; never writes. |
| **[ai-agent-guidelines](https://github.com/swjeong0825/ai-agent-guidelines)** | AI agent coding guidelines used during development. |

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (Browser)                         │
│                                                                   │
│  Chatroom UI ──► Chat-to-Intent Server ──► TLM Backend (this)    │
│  (renders          (LLM intent classifier,   (domain logic,        │
│   responses,        read-only gateway,        PostgreSQL,           │
│   submits           prefilled payload          REST API)            │
│   confirmed         builder)                                       │
│   write forms)                                                     │
└──────────────────────────────────────────────────────────────────┘
```

**Key constraint:** The Chat-to-Intent Server only calls `GET` endpoints on this backend. Confirmed write operations are submitted by the frontend **directly** to this backend — the Chat-to-Intent Server is never in the write path.

## API Reference

Base URL: `http://localhost:8000`

### Player-facing endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/leagues` | Create a new league → returns `league_id` + `host_token`. Requires `title` and `host_email` (RFC-compliant email; immutable; never echoed on read endpoints). |
| `POST` | `/leagues/{league_id}/matches` | Submit a confirmed match result (auto-registers new players/pairs) |
| `POST` | `/leagues/{league_id}/planned-matches` | Atomically upsert proposed matchups by client UUID; no host token required |
| `GET` | `/leagues/{league_id}/planned-matches` | All shared plans, ordered by UUID; no host token required |
| `GET` | `/leagues/{league_id}/standings` | Ranked win/loss standings |
| `GET` | `/leagues/{league_id}/matches` | Match history (most recent first) |
| `GET` | `/leagues/{league_id}/roster` | All registered players and pairs |

### Admin endpoints (require `X-Host-Token` header)

| Method | Path | Description |
|---|---|---|
| `GET` | `/admin/leagues/{league_id}` | Host-only league metadata for the admin UI (V1: `host_email` only). See `Design_Doc/TLMB_Design_doc/13_api_contracts.md` → "Growth direction" before extending the response. |
| `PATCH` | `/admin/leagues/{league_id}/players/{player_id}` | Edit a player's nickname |
| `DELETE` | `/admin/leagues/{league_id}/pairs/{pair_id}` | Delete a pair (no associated matches allowed) |
| `PATCH` | `/admin/leagues/{league_id}/matches/{match_id}` | Correct a match score |
| `DELETE` | `/admin/leagues/{league_id}/matches/{match_id}` | Delete a match record |

### Error → HTTP status mapping

| Error | Status |
|---|---|
| Not found (League / Player / Pair / Match / Planned Match) | 404 |
| Unauthorized (`host_token` mismatch or missing) | 401 |
| Duplicate (title, nickname, pair conflict) | 409 |
| Submitted names do not match the planned sides (`PlannedMatchMismatchError`) | 409 |
| Structural validation (same player, invalid score) | 422 |
| Invalid nickname or planned matchup; invalid/duplicate planned-match IDs | 422 |

### Planned matches and nickname grammar

Planned-match requests and responses use
`{"matches": [{"id": "d315f636-10e5-4265-9b19-fc260e1ed224", "value": "Alice Bob"}]}`.
POST requires at least one record, rejects duplicate IDs and unexpected item fields,
and returns HTTP 200 in request order. Retrying is idempotent; an existing ID updates
only that plan, and omitted plans remain. GET returns all records in ascending UUID
order, including `{"matches": []}` for an empty league. Unknown leagues return 404.

Values are `player1 player2` for singles or `player1,player2 player3,player4` for
doubles, with exactly one ASCII space between equally sized sides. Nicknames must
be nonempty and contain no whitespace or comma. Values retain case, Unicode, and
order exactly. Unknown/repeated names are valid; uploads never resolve participants,
register players/pairs, record results, or change standings or league activity dates.

To record a plan, include optional `planned_match_id` (UUID) in the existing
`POST /leagues/{league_id}/matches` or `/singles-matches` request. All current names
and score fields remain required. The backend checks the plan belongs to the league,
checks its format and normalized names per side, then records the result and
hard-deletes the plan in one transaction. Doubles teammate order may differ; sides
cannot be swapped. Existing recording rules still apply. Missing plans return 404,
format errors return 422, and different participants return 409. Failures roll back
all writes. Success remains 201 with `match_id` and `created_at`.

Omitting the ID or passing null records manually. A retry after successful
consumption returns 404; uploading the deleted ID can recreate it. This recording
option adds no table or migration beyond the existing planned-match migration 015.

Frontend wiring, request examples, UI recovery, and stub replacement are covered in
the [planned-match recording integration guide](docs/planned-match-recording-frontend-guide.md).

Player and alias writes share the same nickname character rule, trim surrounding
ECMAScript whitespace, and retain the backend's existing lowercase normalization.
Existing legacy names remain readable and removable under the usual participation
rules, and can be corrected by renaming. No existing names are migrated.
See [planned-match design](Design_Doc/TLMB_Design_doc/23_planned_matches.md) and
[API contracts](Design_Doc/TLMB_Design_doc/13_api_contracts.md).

Apply migration `015` with `alembic upgrade head` before serving the new endpoints.

## Setup

**Prerequisites:** Python 3.13+, PostgreSQL

```bash
# 1. Clone and enter the project
git clone https://github.com/swjeong0825/TLMB_backend_main.git
cd TLMB_backend_main

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set DATABASE_URL, e.g.:
# DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/tennis_league

# 5. Run database migrations
alembic upgrade head

# 6. Start the server
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Running Tests

```bash
pytest
```
