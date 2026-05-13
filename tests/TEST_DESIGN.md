# Test Suite — Design Notes

> Companion document to [TESTING.md](TESTING.md) (the *how to run* guide).
> This doc covers *how the suite is designed* — what each layer guarantees,
> how database isolation works, and the patterns every test should follow to
> avoid false positives.

---

## 1. The four layers, what each one proves

| Layer | Location | Touches DB? | Touches HTTP? | Proves |
|---|---|---|---|---|
| **Domain** | `tests/domain/` | No | No | Aggregates, value objects, policies, and services enforce invariants in pure Python. |
| **Application** | `tests/application/` | No (mocked) | No | Use cases orchestrate the domain + repositories correctly. Repos are `AsyncMock` instances. |
| **API** | `tests/api/` | No (mocked) | Yes (ASGI in-process) | Routers, schemas, dependency wiring, auth headers, and exception → status mapping work correctly. Use cases are `AsyncMock` instances. |
| **Integration** | `tests/integration/` | **Yes** | No | Real SQLAlchemy + Postgres round-trips: repositories, mappers, ORM cascades, alembic SQL. |
| **E2E** | `tests/e2e/` | **Yes** | Yes (ASGI in-process) | Top-to-bottom: HTTP → router → use case → repository → real Postgres → response. |

The layering deliberately overlaps so the *same* business rule (e.g. "match
submission must reject not-in-allowlist nicknames when the rule is on") is
verified multiple times: once in pure-domain unit tests, once in
mocked-application unit tests, once in API-router unit tests with the use case
mocked, and once end-to-end against real Postgres. Each layer confirms a
different slice of "this still works" and they catch different bug classes.

---

## 2. Database isolation contract

### 2.1 The invariant

> At the start of every integration / e2e test, the test database is empty.
> At the end of every test, the database is reset to empty.

This is enforced by **autouse fixtures** in two conftests:

```78:84:tests/integration/conftest.py
@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tables after every test to keep tests isolated."""
    yield
    async with _engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE leagues CASCADE"))
```

```62:67:tests/e2e/conftest.py
@pytest_asyncio.fixture(autouse=True)
async def clean_db() -> None:
    """Truncate all tables after each test to keep tests isolated."""
    yield
    async with _test_engine.begin() as conn:
        await conn.execute(text("TRUNCATE TABLE leagues CASCADE"))
```

### 2.2 Why `TRUNCATE TABLE leagues CASCADE` is enough

Every child table FKs into `leagues.league_id` with `ON DELETE CASCADE`:

- `players.league_id`
- `teams.league_id`
- `matches.league_id`
- `allowlist_entries.league_id` (added in alembic 005, renamed in alembic 006)

So one statement clears the entire app's data set. When a new table is added,
the only thing the test maintainer needs to confirm is that its FK to
`leagues` declares `ondelete="CASCADE"` — the existing fixture then keeps
working unchanged.

### 2.3 Truncate runs *after*, not *before*, each test

The `yield` is the test running. The TRUNCATE happens after the yield. So the
contract is "previous test left it empty" rather than "current test cleans up
before it starts". The two are equivalent in steady state, but it means that
**the very first test in a freshly-seeded DB will see whatever was already
there** — which is why the integration / e2e suites assume the DB starts at
the alembic head with **no application data**.

### 2.4 Database URL precedence

| Suite | Variables checked, in order | Hard fallback |
|---|---|---|
| Integration | `INTEG_DATABASE_URL` → `DATABASE_URL` | `postgresql+asyncpg://localhost/tennis_league_integ` |
| E2E | `DATABASE_URL` (via `os.environ.setdefault`) | `postgresql+asyncpg://@localhost:5432/tennis_league_e2e` |

Source: [`tests/integration/conftest.py`](integration/conftest.py) and
[`tests/e2e/conftest.py`](e2e/conftest.py).

> **Operational consequence:** if your shell or `.env` exports a
> `DATABASE_URL` pointing at a real environment (e.g. a Neon branch you use
> for development), running the integration or e2e suites **will truncate it
> after every test**. To isolate, point `INTEG_DATABASE_URL` at a separate
> Neon test branch, or unset/override `DATABASE_URL` for that pytest invocation.

---

## 3. The arrange–act–assert contract

The empty-DB-at-start design is **safe only because every test inserts the
data it cares about as part of its own arrange step**, and asserts on
*specific values* (not just "no error").

### 3.1 Examples in the codebase

**Repository test — arranges row, reads it back, asserts on field values.**

```35:47:tests/integration/repositories/test_league_repository.py
async def test_save_and_get_by_id_round_trip(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)
    league = _make_league("Round Trip League")
    await repo.save(league)
    await session.commit()
    session.expire_all()

    found = await repo.get_by_id(league.league_id)

    assert found is not None
    assert found.title == "Round Trip League"
    assert found.host_token.value == "token-abc"
    assert str(found.league_id) == str(league.league_id)
```

If `save()` were silently broken, `found` would be `None`, the
`assert found is not None` would fail, and we'd have caught the bug despite
the empty DB.

**Repository test — bulk insert, expect specific set back.**

```24:43:tests/integration/repositories/test_league_repository_allowlist.py
async def test_save_persists_added_allowlist_entries(session: AsyncSession) -> None:
    repo = SqlAlchemyLeagueRepository(session)

    league = _make_league()
    await repo.save(league)
    await session.commit()
    session.expire_all()

    league = await repo.get_by_id(league.league_id)
    assert league is not None

    league.add_allowlist_entries(["alex", "daniel", "jason"])
    await repo.save(league)
    await session.commit()
    session.expire_all()

    reloaded = await repo.get_by_id(league.league_id)
    assert reloaded is not None
    nicks = {entry.nickname.value for entry in reloaded.allowlist}
    assert nicks == {"alex", "daniel", "jason"}
```

The assertion is a positive equality on the exact set that must be there. A
broken `save()` would make `nicks == set()` and the assertion would fail.

**E2E test — arranges league + allowlist, exercises the rule, asserts on the
structured error payload.**

```174:200:tests/e2e/test_allowlist_api.py
async def test_match_submission_rejected_when_participants_not_allowlisted(
    client: AsyncClient,
) -> None:
    league = await _create_league(
        client, "Allowlist League", require_allowlist=True
    )
    league_id, host_token = league["league_id"], league["host_token"]

    # Allowlist only two of the four submitting players.
    resp = await client.post(
        f"/admin/leagues/{league_id}/allowlist",
        json={"nicknames": ["alice", "bob"]},
        headers={"X-Host-Token": host_token},
    )
    assert resp.status_code == 201

    # Submit a match with two participants not on the allowlist → 422 ...
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "NotInAllowlistError"
    assert sorted(body["missing_nicknames"]) == ["charlie", "diana"]
```

### 3.2 Patterns to use, patterns to avoid

| Pattern | Robust to empty DB? | When to use |
|---|---|---|
| Insert N rows, expect N back | ✅ | Standard happy-path read tests. |
| Insert row X, expect to read X back with specific field values | ✅ | Round-trip tests, mapper coverage. |
| Insert, mutate via endpoint, re-read and verify mutation | ✅ | E2E flows. |
| Don't insert anything, expect 404 on a specific id | ✅ | Lookup-by-id error paths. |
| Don't insert anything, expect empty list | ⚠️ | Only safe when paired with another assertion (e.g. status code 200, downstream behavior). Standalone, this assertion is **always true** on an empty DB. |
| Don't insert anything, expect "no exception raised" | ❌ | This is the textbook false-positive shape. Avoid. |

The one place we deliberately use the "expect empty list" shape is when the
empty list itself *is* the contract being tested, and we always pair it with
at least one other concrete assertion. Example:

```247:262:tests/e2e/test_allowlist_api.py
async def test_default_league_does_not_enforce_allowlist_check(
    client: AsyncClient,
) -> None:
    """The default rules carry require_allowlist=False, so submitting a match
    against an empty allowlist must succeed — preserves byte-for-byte
    compatibility for every league that existed before this feature."""
    league = await _create_league(client, "Default League")
    league_id = league["league_id"]

    # Allowlist is empty.
    resp = await client.get(f"/leagues/{league_id}/allowlist")
    assert resp.status_code == 200
    assert resp.json() == {"allowlist": []}

    # Match submission still succeeds.
    resp = await _submit_match(client, league_id)
    assert resp.status_code == 201, resp.text
```

The test creates a real league first, so the GET returning `{}` is a real
observation about that league — not a degenerate "DB is empty so anything
returns nothing" pass.

### 3.3 How to spot-check a test isn't a false positive

If you ever doubt a particular test, the standard trick is **mutation
testing by hand**: deliberately break the production code path the test is
supposed to cover, then re-run the test. Examples:

| Mutation | Tests that should fail |
|---|---|
| Make `LeagueRepository.save()` an empty `pass` | Most integration repository tests. |
| Make `validate_match_participants_allowed` an unconditional no-op | `test_flag_on_and_missing_nickname_raises_with_payload` (application) and `test_match_submission_rejected_when_participants_not_allowlisted` (e2e). |
| Make the GET allowlist endpoint always return `{"allowlist": []}` | `test_host_can_add_list_and_remove_allowlist_entries` (the post-add list assertion expects 3 sorted names). |
| Make `from_dict` ignore the `require_allowlist` key | `test_from_dict_v5_round_trip`, `test_from_dict_v5_require_allowlist_true`, `test_v5_rules_round_trip_with_require_allowlist_true`. |

If a candidate mutation passes every test, the suite is missing coverage for
that code path.

---

## 4. Layer-specific patterns

### 4.1 Domain (`tests/domain/`)

- Pure in-memory. No fixtures except a few module-level helpers like
  [`_league()`](domain/test_league_aggregate.py) and `_league_otpp_false()`.
- Each test instantiates its own `League`, calls one or two methods, and
  asserts on either a returned value, the resulting state, or a raised
  exception.
- Exceptions are first-class assertions — `pytest.raises(ExceptionType)` is
  used everywhere a domain rule rejects an input.

### 4.2 Application (`tests/application/`)

- Repositories are `AsyncMock` fixtures defined in
  [`tests/application/conftest.py`](application/conftest.py).
- The mock is **arranged** by setting `return_value` (e.g. a real `League`
  built via `make_league()`) so the use case sees exactly the input it
  needs. After the act, we assert on:
  1. The use case's return value.
  2. The state of the in-memory `League` (which the mock returned).
  3. The mock's call history (`save.assert_awaited_once_with(league)`,
     `save.assert_not_awaited()`, etc.).
- Authorization paths (`UnauthorizedError`) always pair the exception
  assertion with `mock.save.assert_not_awaited()` to prove no write happened.

### 4.3 API (`tests/api/`)

- The full FastAPI `app` is loaded once and dependency-overridden in
  [`tests/api/conftest.py`](api/conftest.py) so every use case is an
  `AsyncMock`.
- The DB is **never touched** — `os.environ.setdefault("DATABASE_URL", ...)`
  is set to a placeholder string just so the database module can import
  without crashing.
- Tests assert on HTTP status codes, response JSON shape, and the
  `error` discriminator (`response.json()["error"] == "FooError"`) so a
  silent change in exception → status mapping is caught.

### 4.4 Integration (`tests/integration/`)

- Real Postgres connection, `NullPool` engine to avoid event-loop binding
  issues across pytest-asyncio loops.
- Fixtures provide `session`, `session_factory`, `persisted_league`, and
  `persisted_league_with_match` (see
  [`tests/integration/conftest.py`](integration/conftest.py)). Each fixture
  is responsible for committing its own setup.
- After each test, `clean_db` truncates `leagues CASCADE`.
- Migration tests insert raw rows via `text(INSERT...)`, run the migration's
  SQL via `text(UPDATE...)`, then read back via `text(SELECT...)` — never
  touching the ORM. This isolates the migration logic from any future ORM
  drift.

### 4.5 E2E (`tests/e2e/`)

- Real Postgres + real FastAPI app via `httpx.AsyncClient(ASGITransport(app))`.
- The conftest patches `app.infrastructure.config.database.engine` and
  `AsyncSessionFactory` to a `NullPool` test engine **before** the app is
  imported, to avoid the production pool clinging to a stale event loop.
- Tests use small local helpers (`_create_league`, `_submit_match`) inside
  each file rather than shared fixtures, so each test reads top-to-bottom
  as a complete story.

---

## 5. Test data factories — where new domain fields show up

When the domain model adds a required field (no default), every direct
constructor call needs updating. There are two such constructors used in
tests:

1. `LeagueRules(...)` (the `@dataclass` constructor) — used in two tests
   that validate ranking-calculator behavior. Search:
   ```bash
   rg "LeagueRules\(\s*\n\s*version=" backend_main
   ```
2. `AllowlistEntry(...)`, `Player(...)`, `Team(...)` (entity dataclasses) —
   currently only used inside aggregate methods, not in tests directly.

Production code constructs `LeagueRules` only via:

- `LeagueRules.from_dict(...)` (parses JSONB from the DB, applies upgrades).
- `LeagueRules.default_for_new_league()` (the product default).

So any new field must be:

1. Added to the dataclass (positional or with default).
2. Added to `from_dict` parsing (with a sane default for older versions).
3. Added to `to_dict`.
4. Added to `default_for_new_league`.
5. Added to the two test sites that call `LeagueRules(...)` directly, OR
   given a default in step 1.

For the v5 `require_allowlist` field, the choice was **no default** on the
dataclass + explicit `require_allowlist=False` at the two test call sites.
This forces every future site that builds a `LeagueRules` to think about the
flag, instead of silently inheriting `False`.

---

## 6. Common pitfalls and their counter-tests

| Pitfall | Why it happens | Test that guards against it |
|---|---|---|
| Schema migration silently leaves rows partially upgraded | `WHERE` clause too narrow | [`test_v4_row_with_flag_false_is_renamed_and_bumped`](integration/test_migration_006_allowlist_rename_and_rules_v5.py) |
| Migration is not idempotent (re-run corrupts data) | Forgot to filter by `version` | [`test_upgrade_is_idempotent_for_v5_rows`](integration/test_migration_006_allowlist_rename_and_rules_v5.py) |
| New ORM table not loaded with `selectinload`, causing `MissingGreenlet` at access time | Forgetting to extend the `_LEAGUE_LOAD_OPTIONS` tuple | [`test_save_persists_added_allowlist_entries`](integration/repositories/test_league_repository_allowlist.py) — would raise on the second `get_by_id` |
| Domain method that should not write still writes | Forgot guard | Application tests follow the pattern `with pytest.raises(...): ...` followed by `mock.save.assert_not_awaited()` |
| Exception → HTTP status mapping silently broken | Forgot to register handler in `app/main.py` | API tests assert both `response.status_code == 422` AND `response.json()["error"] == "NotInAllowlistError"` |
| Use case rejects valid input due to over-strict validation | Schema field validator too narrow | API tests include positive-path cases (`test_returns_201_on_success`) alongside negative ones |
| Cross-cutting flag added to one path but missed in another | Lots of paths touch `LeagueRules` | The **layered overlap** — same scenario covered in domain, application, and e2e tests — surfaces the gap. |

---

## 7. Adding a new feature — minimum test menu

When adding a feature in the style of the v5 allowlist work, the expected
test additions are:

1. **Domain** — one `Test{Method}` class per new aggregate method, with
   happy path + every distinct exception path.
2. **Domain (rules)** — if `LeagueRules` changes, add round-trip,
   default, version-upgrade, and rejection cases.
3. **Application** — one test file per new use case: happy path,
   `LeagueNotFoundError`, `UnauthorizedError`, `mock.save.assert_not_awaited()`
   on the unauthorized path, and one negative case from the domain layer that
   surfaces through the use case.
4. **Application (existing use cases that gain new behavior)** — one new
   test class with rule-on / rule-off / normalization cases.
5. **API** — one `Test{EndpointName}` class per new endpoint with: 2xx
   success, missing-auth → 422, wrong-token → 401, not-found → 404, conflict
   → 409 (where applicable), validation error → 422.
6. **Integration (migration)** — happy bump, custom-field preservation,
   idempotency, downgrade.
7. **Integration (repository)** — round-trip, save+reload of new fields,
   pending-delete persistence, no duplicate inserts on re-save.
8. **E2E** — at minimum: full host-managed flow, rule-on rejection with
   structured payload assertion, rule-off no-op (backwards compatibility).

The v5 allowlist work (and the original v4 eligible-players work it renamed)
is a worked example of all eight, and a useful template for the next feature.
