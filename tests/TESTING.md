# Test Suite — Running Guide

All commands must be run from the `backend_main/` directory using the local
virtual environment.  The venv is located at `backend_main/.venv/`.

```
cd backend_main/
```

---

## Quick Reference

| Suite | Needs DB | Command |
|-------|----------|---------|
| Unit | No | `.venv/bin/pytest tests/domain/ tests/application/ tests/api/` |
| Integration | Yes (`tennis_league_integ`) | `.venv/bin/pytest tests/integration/` |
| E2E | Yes (`tennis_league_e2e`) | `.venv/bin/pytest tests/e2e/` |
| All | Yes (both DBs) | `.venv/bin/pytest` |

---

## 1. Unit Tests

**Location:** `tests/domain/`, `tests/application/`, `tests/api/`

No database required.  All external dependencies (repositories, use cases) are
replaced with in-memory mocks.

### Run all unit tests

```bash
.venv/bin/pytest tests/domain/ tests/application/ tests/api/
```

### Run a specific unit test layer

```bash
# Domain layer only (value objects, aggregates, policies, domain services)
.venv/bin/pytest tests/domain/

# Application layer only (use cases with mocked repos)
.venv/bin/pytest tests/application/

# API layer only (HTTP routing with mocked use cases)
.venv/bin/pytest tests/api/
```

### Run a single test file

```bash
.venv/bin/pytest tests/domain/test_league_aggregate.py
```

### Run a single test class or test

```bash
.venv/bin/pytest tests/domain/test_league_aggregate.py::TestRegisterPlayersAndTeam
.venv/bin/pytest tests/domain/test_league_aggregate.py::TestRegisterPlayersAndTeam::test_same_player_listed_twice_raises_same_player_error
```

---

## 2. Integration Tests

**Location:** `tests/integration/`

Requires a running PostgreSQL instance with the schema applied.  These tests
bypass the HTTP layer and talk directly to the database through repositories
and use cases.

### Database setup

```bash
# Create the integration database (one-time)
createdb tennis_league_integ

# Apply the schema via Alembic
ALEMBIC_DATABASE_URL=postgresql+asyncpg://localhost/tennis_league_integ \
  .venv/bin/alembic upgrade head
```

> **Default connection string:** `postgresql+asyncpg://localhost/tennis_league_integ`
> Override with the `INTEG_DATABASE_URL` environment variable.

### Run all integration tests

```bash
.venv/bin/pytest tests/integration/
```

### Run with a custom database URL

```bash
INTEG_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/mydb \
  .venv/bin/pytest tests/integration/
```

### Run a specific integration sub-suite

```bash
# Repository tests only
.venv/bin/pytest tests/integration/repositories/

# Use case tests only
.venv/bin/pytest tests/integration/use_cases/

# Unit of work tests only
.venv/bin/pytest tests/integration/unit_of_work/

# Domain service tests (pure logic, but grouped with integration)
.venv/bin/pytest tests/integration/domain/
```

---

## 3. E2E Tests

**Location:** `tests/e2e/`

Requires a running PostgreSQL instance with the schema applied.  These tests
spin up the full FastAPI application in-process via an `httpx.AsyncClient` and
exercise every endpoint over real database calls.

### Database setup

```bash
# Create the e2e database (one-time)
createdb tennis_league_e2e

# Apply the schema via Alembic
DATABASE_URL=postgresql+asyncpg://localhost/tennis_league_e2e \
  .venv/bin/alembic upgrade head
```

> **Default connection string:** `postgresql+asyncpg://@localhost:5432/tennis_league_e2e`
> Override with the `DATABASE_URL` environment variable.

### Run all e2e tests

```bash
.venv/bin/pytest tests/e2e/
```

### Run with a custom database URL

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/mydb \
  .venv/bin/pytest tests/e2e/
```

### Run a specific e2e file

```bash
.venv/bin/pytest tests/e2e/test_admin_api.py
.venv/bin/pytest tests/e2e/test_league_api.py
```

---

## 4. Run the Full Test Suite

Runs unit, integration, and e2e tests in a single invocation.  Both databases
must be available.

```bash
.venv/bin/pytest
```

With custom database URLs:

```bash
INTEG_DATABASE_URL=postgresql+asyncpg://localhost/tennis_league_integ \
DATABASE_URL=postgresql+asyncpg://localhost/tennis_league_e2e \
  .venv/bin/pytest
```

---

## Useful pytest Flags

| Flag | Purpose |
|------|---------|
| `-v` | Verbose output — show each test name and result |
| `-x` | Stop on first failure |
| `--tb=short` | Shorter traceback format |
| `--tb=no` | Suppress tracebacks entirely (summary only) |
| `-k "keyword"` | Run only tests whose names contain `keyword` |
| `-q` | Quiet mode — minimal output |
| `--co` | Collect (list) tests without running them |

### Examples

```bash
# Verbose unit tests, stop on first failure
.venv/bin/pytest tests/domain/ tests/application/ tests/api/ -v -x

# Run only tests related to nickname
.venv/bin/pytest -k "nickname"

# List all collected unit tests without running them
.venv/bin/pytest tests/domain/ tests/application/ tests/api/ --co -q
```

---

## Environment Variables Summary

| Variable | Used by | Default |
|----------|---------|---------|
| `DATABASE_URL` | E2E tests, app runtime | `postgresql+asyncpg://@localhost:5432/tennis_league_e2e` |
| `INTEG_DATABASE_URL` | Integration tests | `postgresql+asyncpg://localhost/tennis_league_integ` |
