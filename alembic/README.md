# Alembic — Database Migration Guide

This directory manages all database schema migrations for the Tennis League Manager backend using [Alembic](https://alembic.sqlalchemy.org/).

---

## Prerequisites

- PostgreSQL running locally (or a remote instance)
- `.env` file configured at `backend_main/.env` with a valid `DATABASE_URL`
- Python virtual environment activated (`.venv/`)

---

## Setup

### 1. Configure the database URL

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```
DATABASE_URL=postgresql+asyncpg://postgres:password@localhost:5432/tennis_league
```

### 2. Create the database (first time only)

Alembic does **not** create the database itself — only the tables inside it. Create the database manually first:

```bash
psql -U postgres -c "CREATE DATABASE tennis_league;"
```

---

## Common Commands

All commands must be run from the `backend_main/` directory with `PYTHONPATH=.` so the app modules resolve correctly.

### Apply all pending migrations (create tables)

```bash
PYTHONPATH=. .venv/bin/alembic upgrade head
```

This runs every migration in `alembic/versions/` that has not been applied yet. On a fresh database this creates all 4 tables: `leagues`, `players`, `teams`, `matches`.

### Check the current applied revision

```bash
PYTHONPATH=. .venv/bin/alembic current
```

### View migration history

```bash
PYTHONPATH=. .venv/bin/alembic history --verbose
```

### Roll back the most recent migration

```bash
PYTHONPATH=. .venv/bin/alembic downgrade -1
```

### Roll back all migrations (drop all tables)

```bash
PYTHONPATH=. .venv/bin/alembic downgrade base
```

---

## Adding a New Migration

When you change the ORM models in `app/infrastructure/persistence/models/orm_models.py`, generate a new migration file:

```bash
PYTHONPATH=. .venv/bin/alembic revision --autogenerate -m "short description of change"
```

Alembic compares the current database schema against the SQLAlchemy metadata and generates a migration file in `alembic/versions/`. Always review the generated file before applying it — autogenerate is not always 100% accurate.

Then apply it:

```bash
PYTHONPATH=. .venv/bin/alembic upgrade head
```

---

## Directory Structure

```
alembic/
├── env.py                          # Alembic runtime config (async SQLAlchemy setup)
├── versions/
│   └── 001_initial_schema.py       # Initial migration: creates all 4 tables
└── README.md                       # This file
```

### `env.py`

Configures Alembic to run in async mode using the same `DATABASE_URL` as the application. It imports the SQLAlchemy `Base` metadata so `--autogenerate` can detect schema diffs automatically.

### `versions/001_initial_schema.py`

Creates the following tables with all constraints and indexes:

| Table | Description |
|---|---|
| `leagues` | League root — title, host token, description |
| `players` | Players auto-registered on first match submission |
| `teams` | Doubles pairs; each player belongs to at most one team per league |
| `matches` | Match results; references two teams and stores set scores |

---

## Troubleshooting

### `DuplicateTableError: relation "X" already exists`

This error means the table already exists in the database but Alembic has no record of the migration being applied (the `alembic_version` table is missing or empty).

**Common cause on macOS — two separate PostgreSQL servers**

macOS often ends up with two independent PostgreSQL instances running simultaneously (e.g. one from Homebrew, one from Postgres.app). They communicate through different channels:

| | Unix Socket | TCP `localhost:5432` |
|---|---|---|
| How to connect | `psql -d mydb` (no `-h`) | `psql -h localhost -p 5432 -d mydb` |
| How asyncpg connects | — | via the `host=localhost` in `DATABASE_URL` |

These are fully separate servers with separate data directories. A table in one is completely invisible to the other. This causes a confusing situation where `\dt` in psql shows no tables, yet Alembic reports the table already exists — because they are looking at different servers.

**Diagnosis**

Connect using the same parameters as asyncpg (TCP, explicit host and port):

```bash
psql -h localhost -p 5432 -U <your_user> -d tennis_league_test
```

Then check for the conflicting table:

```sql
SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'leagues';
```

If the table appears here but not in a plain `psql -d tennis_league_test` session, you have two servers.

**Fix**

Drop the existing tables from the TCP instance, then re-run migrations:

```bash
psql -h localhost -p 5432 -U <your_user> -d tennis_league_test \
  -c "DROP TABLE IF EXISTS matches, teams, players, leagues CASCADE;"

PYTHONPATH=. .venv/bin/alembic upgrade head
```

**Prevention**

Always use `-h localhost -p 5432` when running `psql` manually so it connects to the same server as the application:

```bash
psql -h localhost -p 5432 -U <your_user> -d tennis_league_test
```

Or export these environment variables in your shell profile so psql defaults to TCP:

```bash
export PGHOST=localhost
export PGPORT=5432
```

---

## Typical Local Development Flow

```bash
# 1. Start PostgreSQL (e.g. via Docker)
docker run -d --name tlm-db -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:16

# 2. Create the database
psql -U postgres -h localhost -c "CREATE DATABASE tennis_league;"

# 3. Apply migrations
PYTHONPATH=. .venv/bin/alembic upgrade head

# 4. Start the app
PYTHONPATH=. .venv/bin/uvicorn app.main:app --reload
```
