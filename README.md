# TLM Backend

Domain logic, PostgreSQL persistence, and REST API for the **Tennis League Manager (TLM)** — a lightweight system that lets a recreational doubles tennis group run a league with no login system and no manual registration.

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
| `POST` | `/leagues` | Create a new league → returns `league_id` + `host_token` |
| `POST` | `/leagues/{league_id}/matches` | Submit a confirmed match result (auto-registers new players/teams) |
| `GET` | `/leagues/{league_id}/standings` | Ranked win/loss standings |
| `GET` | `/leagues/{league_id}/matches` | Match history (most recent first) |
| `GET` | `/leagues/{league_id}/roster` | All registered players and teams |

### Admin endpoints (require `X-Host-Token` header)

| Method | Path | Description |
|---|---|---|
| `PATCH` | `/admin/leagues/{league_id}/players/{player_id}` | Edit a player's nickname |
| `DELETE` | `/admin/leagues/{league_id}/teams/{team_id}` | Delete a team (no associated matches allowed) |
| `PATCH` | `/admin/leagues/{league_id}/matches/{match_id}` | Correct a match score |
| `DELETE` | `/admin/leagues/{league_id}/matches/{match_id}` | Delete a match record |

### Error → HTTP status mapping

| Error | Status |
|---|---|
| Not found (League / Player / Team / Match) | 404 |
| Unauthorized (`host_token` mismatch or missing) | 401 |
| Duplicate (title, nickname, team conflict) | 409 |
| Structural validation (same player, invalid score) | 422 |

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
