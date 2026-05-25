# `backend_main/` — Agent Guide

Python / FastAPI / PostgreSQL backend for the Tennis League Manager.
**This package owns all domain state.** Every business rule, every
invariant, and the only writable database in the system live here.

## Read first

- `memory-bank/projectbrief.md`, `systemPatterns.md`, `techContext.md`
  (repo root) — the cross-cutting context.
- This file.
- `Design_Doc/TLMB_Design_doc/15_build_order.md` — the order in which
  the design was built and the order an agent should follow when
  extending.

## Layering — one rule, no exceptions

```
api/             FastAPI routers, Pydantic request/response schemas.
application/     Use cases (one class per command/query), Unit-of-Work boundary.
domain/          Aggregate roots, value objects, policies, domain errors.
                 NO FastAPI, NO SQLAlchemy, NO httpx imports here. Ever.
infrastructure/  ORM mappers, repository implementations, alembic migrations,
                 external clients.
```

Dependency arrows: `api → application → domain` and
`infrastructure → application/ports`. Domain depends on nothing.

If you find yourself wanting to import FastAPI from `application/`,
or import SQLAlchemy from `domain/`, stop and read
`.cursor/rules/backend-ddd-layering.mdc`.

## Where each concept lives

| Concept | Location |
|---|---|
| Aggregate roots | `app/domain/aggregates/<name>/aggregate_root.py` |
| Value objects | `app/domain/aggregates/<name>/value_objects.py` (or local) |
| Policies | `app/domain/aggregates/<name>/policies.py` |
| Domain errors | `app/domain/aggregates/<name>/errors.py` |
| Use cases | `app/application/use_cases/<command_or_query>.py` |
| Repository ports | `app/application/ports/` or `app/domain/repositories/` |
| ORM mappers | `app/infrastructure/persistence/mappers/` |
| Repository implementations | `app/infrastructure/persistence/repositories/` |
| Routers | `app/api/routers/` |
| Schemas | `app/api/schemas/` |
| Composition root | `app/dependencies.py` |
| Migrations | `alembic/versions/` |
| Tests | `tests/` (unit / integration / e2e) |

## Design doc index (`Design_Doc/TLMB_Design_doc/`)

| # | Topic |
|---|---|
| 00 | System scope |
| 01 | Bounded contexts + glossary |
| 02 | Business actions |
| 03 | Business invariants |
| 04 | Candidate aggregates |
| 05 | Aggregate designs (`league.md`, `match.md`) |
| 06 | Domain services |
| 07 | Ports and repositories |
| 08 | Unit of Work and transactions |
| 09 | Application use cases |
| 10 | Workflows |
| 11 | Read models and queries |
| 12 | Persistence strategy |
| 13 | API contracts |
| 14 | Implementation readiness |
| 15 | **Build order** ← canonical sequence |
| 16 | League rules and match policies |
| 17 | Configurable ranking (v2) |
| 18 | Configurable ranking v3 |
| 19 | v3 build order |
| 20 | Roster pre-registration |

ADRs live separately in `Design_Doc/Technical_Descision/`.

## Patterns the codebase relies on

### Aggregate-first writes
A use case loads the relevant aggregate via its repository, invokes a
domain method, and persists through the repository. **No domain
service coordinates cross-aggregate persistence in V1.** Implicit
player/team registration is performed inside the `League` aggregate's
`register_players_and_team` method, called from
`SubmitMatchResultUseCase` inside a Unit of Work. See
`08_unit_of_work_and_transactions.md` and `09_application_use_cases.md`.

### Policies (stateless predicates)
See `harness_notes/01_when_to_extract_a_policy.md` and
`.cursor/rules/backend-policy-vs-method.mdc`. Today: `NicknameUniquenessPolicy`,
`OneTeamPerPlayerPolicy`, `RosterMembershipPolicy`. The rule-flag gate
(e.g. `if not rules.auto_register_players_on_match:`) lives at the call
site on the aggregate, not inside the policy.

### `LeagueRules`
Per-league JSONB configuration with a fixed value set:
`one_team_per_player`, `match_pair_idempotency`, `ranking_subject`,
`tie_breakers`, `auto_register_players_on_match`. Versioned (current
schema is v7), immutable after league creation. The league timezone
is a separate `League` field/DB column, not a `LeagueRules` key. See
`16_league_rules_and_match_policies.md`.

### Error → HTTP status mapping
Owned by the API layer; the domain raises domain errors, the use case
re-raises (or maps), and the router translates to HTTP. The mapping
table lives in `README.md` and in `13_api_contracts.md`.

| Error | Status |
|---|---|
| Not found (League / Player / Team / Match) | 404 |
| Unauthorized (`host_token` mismatch / missing) | 401 |
| Duplicate (title, nickname, team conflict) | 409 |
| Structural validation (same player, invalid score) | 422 |

## Tests

- Unit: pure-domain tests under `tests/domain/`. Fast, no I/O.
- Integration: tests that exercise the use case + UoW + a real
  database (or in-memory fake) under `tests/application/`.
- E2E: HTTP-level tests under `tests/e2e/` (or `tests/api/`).

Run all: `pytest`.

See `tests/TEST_DESIGN.md` and `tests/TESTING.md` for the test-shape
expectations.

## Adding a new use case (the standard checklist)

1. Add or update the aggregate method in `app/domain/aggregates/<name>/`.
2. Write or update unit tests under `tests/domain/`.
3. Add the use case under `app/application/use_cases/<name>.py`.
4. Add the API router and schemas under `app/api/`.
5. Wire the dependency in `app/dependencies.py`.
6. Add an alembic migration if persistence changed.
7. Update the relevant design doc (likely under
   `Design_Doc/TLMB_Design_doc/`).
8. Add at least one E2E test exercising the new endpoint.

The future `add-use-case` Cursor Skill (`ai_development_brainstorm.html`
§3.2) will wrap this checklist.

## Local commands

```bash
cd backend_main
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # edit DATABASE_URL
alembic upgrade head
uvicorn app.main:app --reload   # http://localhost:8000
pytest
```
