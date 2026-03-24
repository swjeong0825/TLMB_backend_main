# Implementation Readiness

## Ready Now

### Domain layer

- **League aggregate** (`domain/aggregates/league/`) — fully designed in `05_aggregate_designs/league.md`:
  - `aggregate_root.py`: `League.create`, `register_players_and_team`, `edit_player_nickname`, `delete_team`
  - `entities.py`: `Player` (with `PlayerNickname`), `Team`
  - `value_objects.py`: `LeagueId`, `HostToken`, `PlayerNickname`, `PlayerId`, `TeamId`
  - `policies.py`: `NicknameUniquenessPolicy`, `OneTeamPerPlayerPolicy`
  - `repository.py`: `LeagueRepository` abstract interface
- **Match aggregate** (`domain/aggregates/match/`) — fully designed in `05_aggregate_designs/match.md`:
  - `aggregate_root.py`: `Match.create`, `Match.edit_score`
  - `value_objects.py`: `MatchId`, `SetScore`
  - `repository.py`: `MatchRepository` abstract interface
- **Domain service** (`domain/services/`): `StandingsCalculator` — fully specified in `06_domain_services.md`
- **Domain events** (`domain/events.py`): `LeagueCreated`, `PlayersAndTeamRegistered`, `PlayerNicknameEdited`, `TeamDeleted` — define data classes only; no event bus wiring in V1 (no consumer concern identified)

### Application layer

- **Unit of Work interface** (`application/unit_of_work/`):
  - `base.py`: shared abstract UoW contract (`__aenter__`, `__aexit__`, `commit`, `rollback`)
  - `submit_match_result_uow.py`: abstract `SubmitMatchResultUnitOfWork` exposing `league_repo: LeagueRepository` and `match_repo: MatchRepository`
- **Use cases** (`application/use_cases/`) — all 9 use cases fully defined in `09_application_use_cases.md`:
  - `create_league_use_case.py`
  - `submit_match_result_use_case.py`
  - `get_standings_use_case.py`
  - `get_match_history_use_case.py`
  - `get_league_roster_use_case.py`
  - `edit_player_nickname_use_case.py`
  - `delete_team_use_case.py`
  - `edit_match_score_use_case.py`
  - `delete_match_use_case.py`
- No workflows required (`10_workflows.md` — no workflow coordinator needed in V1)
- No external ports required (`07_ports_and_repositories.md` — only PostgreSQL via repositories)

### Infrastructure layer

- **Database config** (`infrastructure/config/database.py`): SQLAlchemy async engine + `AsyncSession` factory using asyncpg driver; Alembic for migrations — toolchain confirmed in `12_persistence_strategy.md`
- **ORM models** (`infrastructure/persistence/models/`): 4 tables — `leagues`, `players`, `teams`, `matches` — with all columns, FK constraints, and unique indexes specified in `12_persistence_strategy.md`
- **Mappers** (`infrastructure/persistence/mappers/`):
  - `league_mapper.py`, `player_mapper.py`, `team_mapper.py`, `match_mapper.py`
  - Value object reconstruction rules (`PlayerNickname`, `SetScore`, typed UUID wrappers) all documented
- **Repository implementations** (`infrastructure/persistence/repositories/`):
  - `league_repository.py`: implements all 4 `LeagueRepository` methods including `get_by_id_with_lock` (`SELECT ... FOR UPDATE`)
  - `match_repository.py`: implements all 5 `MatchRepository` methods including hard `delete`
- **Concrete UoW** (`infrastructure/persistence/unit_of_work/submit_match_result_uow.py`): wires `LeagueRepository` and `MatchRepository` to a single shared `AsyncSession`
- **Alembic migration**: initial migration creating all 4 tables with constraints and indexes

### API layer

- **Request/response schemas** (`api/schemas/`): shapes for all 9 endpoints fully defined in `13_api_contracts.md`
- **Routers** (`api/routers/`):
  - `league_router.py`: 5 player-facing endpoints (POST `/leagues`, POST `/leagues/{league_id}/matches`, GET standings/matches/roster)
  - `admin_router.py`: 4 admin endpoints under `/admin/leagues/...` gated by `X-Host-Token` header
- **Dependency wiring** (`dependencies.py`): composition root binding abstract interfaces to concrete implementations
- **App entrypoint** (`main.py`): FastAPI app creation, router registration

---

## Blocked By

- Domain layer blocked by: nothing — all design decisions resolved
- Application layer blocked by: nothing — domain interfaces and UoW boundaries are fully specified
- Infrastructure layer blocked by: nothing — schema, ORM toolchain, and mapper responsibilities are fully specified
- API layer blocked by: nothing — all endpoint contracts, error codes, and auth model are fully specified

---

## Missing Decisions

- None. All open questions from the aggregate design documents have been resolved:
  - Draw handling in V1: draws contribute zero wins/losses (resolved in `06_domain_services.md`)
  - Single set per match in V1: one `SetScore` pair per match (resolved in `05_aggregate_designs/match.md`)
  - Canonical player ID ordering on `teams` table: lower UUID stored as `player_id_1` (resolved in `12_persistence_strategy.md`)
  - `created_at` as match ordering field: infrastructure-managed DB column used in V1 instead of a domain `recorded_at` (resolved in `11_read_models_and_queries.md`)
  - `hostToken` stored plaintext: accepted in V1; no hashing or rotation (resolved in `05_aggregate_designs/league.md`)
  - Domain events: define data classes only, no event bus wiring (resolved in `05_aggregate_designs/league.md`)

---

## Recommended Next Coding Step

- Begin with **Phase 1 — Domain layer** (see `15_build_order.md`):
  - Start with `domain/aggregates/league/value_objects.py` and `domain/aggregates/match/value_objects.py` (no dependencies within the domain layer)
  - Then `domain/aggregates/league/entities.py`, `policies.py`, `aggregate_root.py`
  - Then `domain/aggregates/match/aggregate_root.py`
  - Then `domain/services/standings_calculator.py`
  - Then `domain/events.py`
  - Finally the two abstract `repository.py` interfaces
  - Write unit tests immediately alongside each file — domain code is framework-independent and fully testable without a DB

