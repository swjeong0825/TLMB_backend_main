# Eligible Players (League rules v4)

## Purpose

`eligible_players` is a host-managed list of player nicknames that are
**allowed to participate** in a given league. It is distinct from the
**roster** (`league.players` / `league.teams`, which records players who have
already played) and from **match participants** (the four nicknames on a
specific recorded match):

| Concept | Meaning | Owner |
|---|---|---|
| `eligible_players` | Pre-declared, host-curated allowlist of nicknames who *may* participate. | League aggregate (this doc). |
| `players` (roster) | Players who have already been implicitly registered through a match submission. | League aggregate (existing). |
| `match_participants` | The four nicknames recorded on a single `Match`. | Match aggregate (existing). |

Source guide: [eligible_players_ai_agent_guide.md](../../../eligible_players_ai_agent_guide.md).

## Scope of this iteration

This doc specifies the **backend** feature only. Two thin context docs at the
repo root capture the follow-on work:

- `eligible_players_chat_intents_context.md` (Chat-to-Intent Server)
- `eligible_players_frontend_context.md` (vanilla-JS frontend)

In-scope (this iteration):

- New domain entity `EligiblePlayer` carried inside the `League` aggregate.
- Three new use cases (`AddEligiblePlayers`, `RemoveEligiblePlayer`,
  `GetEligiblePlayers`) and three new HTTP endpoints.
- A new opt-in `LeagueRules` field `require_eligible_players: bool`
  (default `false`) gating match-submission rejection.
- `LeagueRules` schema bump to **v4** plus alembic migration `005`.

Out of scope:

- No automatic backfill of existing `players` rows into `eligible_players`
  (would conflate "joined" with "eligible").
- No mutation API for `LeagueRules.require_eligible_players` after league
  creation — rules remain immutable per
  [16_league_rules_and_match_policies.md](16_league_rules_and_match_policies.md).
- No changes to the chat-to-intent server or frontend in this iteration.

## Domain model

### Aggregate placement

`eligible_players` lives **inside the existing `League` aggregate**, alongside
`players` and `teams`. The eligibility check is per-league, runs in the same
transaction as match submission, and is gated by the host token — exactly the
same consistency boundary used by the existing roster invariants.

```mermaid
flowchart TD
    subgraph LEAGUE [League aggregate]
        ROOT[League root]
        subgraph ENT [Internal entities]
            PE[Player]
            TE[Team]
            EP[EligiblePlayer]
        end
        subgraph VOS [Value objects]
            EPI[EligiblePlayerId]
            PN[PlayerNickname]
            LR["LeagueRules v4 (adds require_eligible_players)"]
        end
    end
    ROOT -->|"creates / removes"| EP
    ROOT -->|"validates against"| EP
    ROOT -->|"holds"| LR
    EP -->|"identified by"| EPI
    EP -->|"holds"| PN
```

### `EligiblePlayer` entity

- Identity: `EligiblePlayerId` (UUID; new value object mirroring `PlayerId`).
- Fields: `eligible_player_id`, `nickname` (reuses the existing
  `PlayerNickname` value object — case-insensitive, stripped, lowercased).
- Lifecycle: created by `League.add_eligible_players`, removed by
  `League.remove_eligible_player`. **Never mutated in place.** A nickname
  change is a remove-then-add.

### Why a separate entity instead of folding into `Player`

- Eligibility is **prospective**; a `Player` row implies past participation.
- Eligible nicknames may never play and should not pollute roster / standings
  reads.
- Removing a nickname from the eligible list must not delete a `Player`
  record (which is FK'd by `Team` and `Match`).

### `League` aggregate methods (added in this iteration)

```python
def add_eligible_players(self, nicknames: list[str]) -> list[EligiblePlayer]:
    """Atomic batch add. Raises EligiblePlayerNicknameAlreadyExistsError if
    any input nickname (after normalization) duplicates an existing eligible
    nickname or another nickname inside the same batch. On error, no entries
    are added."""

def remove_eligible_player(self, eligible_player_id: str) -> None:
    """Raises EligiblePlayerNotFoundError if the id is not in the league.
    Removed ids are appended to `pending_deleted_eligible_player_ids` so the
    repository can DELETE the row on save."""

def validate_match_participants_eligible(self, nicknames: Iterable[str]) -> None:
    """No-op when self.rules.require_eligible_players is False. When True,
    delegates the diff to EligiblePlayerAllowlistPolicy and raises
    IneligiblePlayerError with .missing_nicknames listing every input
    nickname not present in the eligible list."""
```

`pending_deleted_eligible_player_ids` mirrors the existing
`pending_deleted_team_ids` pattern (see
[05_aggregate_designs/league.md](05_aggregate_designs/league.md)).

### `EligiblePlayerAllowlistPolicy`

The diff computation lives in a dedicated policy
(`domain/aggregates/league/policies.py`) rather than inline on the aggregate
method, mirroring `NicknameUniquenessPolicy` and `OneTeamPerPlayerPolicy`:

```python
class EligiblePlayerAllowlistPolicy:
    def find_missing_nicknames(
        self,
        candidates: Iterable[PlayerNickname],
        eligible_players: list[EligiblePlayer],
    ) -> list[str]:
        ...
```

**Two intentional separations** future iterations should preserve:

1. **The rule-flag gate (`if self.rules.require_eligible_players: return`)
   stays on the aggregate method, NOT inside the policy.** Each call site
   that consults the policy decides whether and how to gate. This is the same
   pattern as `OneTeamPerPlayerPolicy`, which is wrapped by
   `if enforce_one_team:` inside `register_players_and_team`. When
   `edit_player_nickname` (the named next caller) starts consulting the
   policy, it gets to choose its own gate semantics — e.g. only enforce the
   rule when the *new* nickname is being changed to something not already
   present as a roster `Player`.
2. **The exception (`IneligiblePlayerError(...)`) is raised by the
   aggregate method, not by the policy.** Different call sites may want
   different error messages while sharing the same `missing_nicknames`
   payload shape (the chat agent and frontend depend on that contract).

The policy is preemptively extracted at single-call-site state because
`edit_player_nickname` is a committed next iteration. See
`backend_main/harness_notes/01_when_to_extract_a_policy.md` for the
decision rule.

### Invariants

- **Nickname uniqueness within the eligible list (case-insensitive).** Two
  entries with the same normalized nickname cannot coexist.
- **Eligible list is independent of the roster.** A nickname may be in
  `eligible_players` without being in `players`, and vice versa. (The latter
  is possible for any league created before the host populates the list, or
  for any league with `require_eligible_players=false`.)
- **`require_eligible_players` is consulted only at match submission.** Add
  / remove operations on the eligible list are always allowed regardless of
  the flag; the flag only changes whether `SubmitMatchResultUseCase` calls
  `validate_match_participants_eligible`.

## `LeagueRules` v4

v4 adds one field to v3:

| Field | Type | Default | Meaning |
|---|---|---|---|
| `require_eligible_players` | `bool` | `false` | When `true`, `SubmitMatchResultUseCase` rejects any submission whose four nicknames include one not present in `eligible_players`. When `false`, the eligible list is informational only (the chat agent may still consult it for name resolution; backend never blocks). |

All other v3 fields are unchanged. The v3 cross-rule
(`(player, OTPP=true)` is rejected) is preserved verbatim.

`LeagueRules.from_dict` accepts inputs of `version` 1, 2, 3, or 4. For inputs
with `version < 4` the `require_eligible_players` key is defaulted to
`false` (mirroring how v1 inputs default `ranking_subject` and
`tie_breakers`). The returned object always has `version=4`.

`LeagueRules.default_for_new_league()` returns
`require_eligible_players=false` so a newly created league with no `rules`
body in the request behaves identically to today.

## Persistence

### New table `eligible_players`

```sql
CREATE TABLE eligible_players (
    eligible_player_id  UUID PRIMARY KEY,
    league_id           UUID NOT NULL
        REFERENCES leagues(league_id) ON DELETE CASCADE,
    nickname_normalized TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (league_id, nickname_normalized)
);
CREATE INDEX ix_eligible_players_league_id ON eligible_players(league_id);
```

Schema mirrors `players`: same FK/cascade semantics, same case-insensitive
uniqueness shape. There is **no** FK from `eligible_players` to `players`;
the two are decoupled by design.

### `leagues.rules` JSONB

No DDL change — the `require_eligible_players: false` key is added to every
existing row's JSONB and the `version` is bumped to `4`.

### Alembic 005

Single migration that does both (one logical unit):

```python
revision = "005"
down_revision = "004"

def upgrade() -> None:
    # 1. Create the new table + index.
    op.create_table("eligible_players", ...)
    op.create_index("ix_eligible_players_league_id", "eligible_players", ["league_id"])

    # 2. Bump every v3 leagues.rules row to v4 with require_eligible_players=false.
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE leagues "
        "SET rules = rules || CAST(:patch AS jsonb) "
        "WHERE (rules->>'version')::int = 3"
    ), {"patch": json.dumps({"version": 4, "require_eligible_players": False})})

def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "UPDATE leagues "
        "SET rules = rules || CAST(:patch AS jsonb) "
        "WHERE (rules->>'version')::int = 4"
    ), {"patch": json.dumps({"version": 3})})
    op.drop_index("ix_eligible_players_league_id", table_name="eligible_players")
    op.drop_table("eligible_players")
```

The JSONB `||` merge keeps the `require_eligible_players` key on downgrade
(harmless extra key — `LeagueRules.from_dict` for v3 ignores it). The
forward bump is idempotent because of the `WHERE` clause.

## Application layer

### New use cases

| Use case | Writes? | UoW? | Auth |
|---|---|---|---|
| `AddEligiblePlayersUseCase` | yes | no | `X-Host-Token` |
| `RemoveEligiblePlayerUseCase` | yes | no | `X-Host-Token` |
| `GetEligiblePlayersUseCase` | no | no | `league_id` only |

All three follow the same shape as the existing roster use cases (e.g.
[`EditPlayerNicknameUseCase`](../../../app/application/use_cases/edit_player_nickname_use_case.py)
for writes, [`GetLeagueRosterUseCase`](../../../app/application/use_cases/get_league_roster_use_case.py)
for reads). Writes use `get_by_id_with_lock`; reads use `get_by_id`.

### Modified use case: `CreateLeagueUseCase`

`CreateLeagueUseCase` accepts an optional bootstrap list so a host can seed
the allowlist **in the same transaction** as the league row itself — a
common workflow when a host turns the new `require_eligible_players` flag
on at creation time and already knows who is invited.

```python
@dataclass
class CreateLeagueCommand:
    title: str
    description: str | None
    rules: dict[str, Any] | None = None
    eligible_players: list[str] = field(default_factory=list)  # NEW
```

Use-case shape (new line only):

```python
league = League.create(command.title, command.description, host_token, rules=rules_vo)

if command.eligible_players:                                   # NEW
    league.add_eligible_players(command.eligible_players)      # NEW

await self._league_repo.save(league)
```

Single-transaction guarantee: the FastAPI request scope owns the
`AsyncSession`. Both the new `LeagueORM` row and every `EligiblePlayerORM`
row are added to that session by one `repo.save(league)` call, and the
session commits at request completion. Either both reach the database or
neither does. There is no second admin call, so the host token returned
to the client is **already** backed by a populated allowlist.

Validation / error shape (delegated entirely to existing layers — nothing
new in the use case):

- Empty list → no-op (`if command.eligible_players:` short-circuits;
  byte-identical to the pre-iteration behavior).
- Blank-string entries → rejected at the API layer by
  `CreateLeagueRequest.eligible_player_nicknames_must_be_non_blank` (422).
- In-batch duplicate (after normalization) → `League.add_eligible_players`
  raises `EligiblePlayerNicknameAlreadyExistsError` **before** `save` is
  called, so the league row is never persisted (409). Verified by the
  `test_duplicate_seeded_eligible_player_rejects_whole_creation`
  integration test.

**Independence from `require_eligible_players`.** The bootstrap list may
be present even when the flag is `false`; the allowlist is populated but
the rule isn't enforced. This is intentional symmetry with the post-create
`POST /admin/leagues/{league_id}/eligible-players` flow, which is also
gated only by the host token, not by the flag.

### Modified use case: `SubmitMatchResultUseCase`

A single new line, just after `get_by_id_with_lock`:

```python
league = await uow.league_repo.get_by_id_with_lock(league_id)
if league is None:
    raise LeagueNotFoundError(...)
league.validate_match_participants_eligible([t1_n1, t1_n2, t2_n1, t2_n2])  # NEW
_, team1 = league.register_players_and_team(t1_n1, t1_n2)
...
```

When `require_eligible_players=false` (every existing league after the
migration) this is a no-op and behavior is byte-identical to today.

## API

### New endpoints

| Method | Path | Auth | Use case |
|---|---|---|---|
| `GET` | `/leagues/{league_id}/eligible-players` | league_id | `GetEligiblePlayersUseCase` |
| `POST` | `/admin/leagues/{league_id}/eligible-players` | league_id + `X-Host-Token` | `AddEligiblePlayersUseCase` |
| `DELETE` | `/admin/leagues/{league_id}/eligible-players/{eligible_player_id}` | league_id + `X-Host-Token` | `RemoveEligiblePlayerUseCase` |

### Modified endpoint: `POST /leagues`

`CreateLeagueRequest` (see [13_api_contracts.md](13_api_contracts.md))
gains an optional `eligible_players: list[str]` field with default `[]`:

```json
{
  "title": "Summer Doubles 2026",
  "description": "Invite-only club tournament",
  "rules": {
    "version": 4,
    "match_pair_idempotency": "once_per_league",
    "one_team_per_player": true,
    "ranking_subject": "team",
    "tie_breakers": ["matches_won"],
    "require_eligible_players": true
  },
  "eligible_players": ["Alex", "Daniel", "Jason"]
}
```

Behavior summary:

- Default `[]`: identical to the pre-iteration behavior (no eligible-player
  rows created, no migration churn).
- Non-empty list: persisted in the same transaction as the league row.
- Validation: each entry must be a non-blank string (422 from pydantic);
  in-batch duplicates after `PlayerNickname` normalization → 409
  `EligiblePlayerNicknameAlreadyExistsError` (league row not created).

### Request / response shapes

`GET /leagues/{league_id}/eligible-players` → `200`

```json
{
  "eligible_players": [
    { "eligible_player_id": "uuid", "nickname": "alex" }
  ]
}
```

`POST /admin/leagues/{league_id}/eligible-players` → `201`

```json
// Request
{ "nicknames": ["Alex", "Daniel", "Jason"] }

// Response
{
  "eligible_players": [
    { "eligible_player_id": "uuid", "nickname": "alex" },
    { "eligible_player_id": "uuid", "nickname": "daniel" },
    { "eligible_player_id": "uuid", "nickname": "jason" }
  ]
}
```

The bulk-batch shape matches the natural "host pre-populates the list"
workflow and is atomic — any duplicate (vs existing entries or within the
batch) rejects the entire request with 409. Single-add is just a one-element
list.

`DELETE /admin/leagues/{league_id}/eligible-players/{eligible_player_id}` → `204`

### New error → HTTP status mapping

| Domain error | HTTP status | Notes |
|---|---|---|
| `EligiblePlayerNotFoundError` | 404 | Unknown `eligible_player_id` for this league. |
| `EligiblePlayerNicknameAlreadyExistsError` | 409 | At least one nickname in the bulk POST duplicates another (existing or in-batch). |
| `IneligiblePlayerError` | 422 | Submitted match contains nicknames not in the eligible list (only when `require_eligible_players=true`). Body includes `missing_nicknames: ["..."]` so clients can render the list verbatim. |

Existing mappings are unchanged. See
[13_api_contracts.md](13_api_contracts.md) for the full table.

`IneligiblePlayerError` JSON body:

```json
{
  "error": "IneligiblePlayerError",
  "detail": "...",
  "missing_nicknames": ["michael", "ryan"]
}
```

The `missing_nicknames` field is contractual — it's the integration point
for the future chat-server clarification flow described in
`eligible_players_chat_intents_context.md`.

## Build order

1. **Domain.** Add `EligiblePlayerId`, `EligiblePlayer`, `League`
   methods, `LeagueRules` v4 with `require_eligible_players`, three new
   exception classes.
2. **Application.** Three new use cases; modify
   `SubmitMatchResultUseCase` to call `validate_match_participants_eligible`;
   extend `CreateLeagueUseCase` with the optional `eligible_players`
   bootstrap list.
3. **Infrastructure.** `EligiblePlayerORM`, mapper, `LeagueORM` relationship,
   repository read+save changes. The repository's existing `save(league)`
   already iterates `league.eligible_players` and inserts any new entries
   via the same session — no additional infrastructure work is needed for
   inline seeding.
4. **Migration.** Alembic 005 (table + JSONB v3→v4 bump).
5. **API.** Pydantic schemas (including the optional `eligible_players`
   field on `CreateLeagueRequest` with non-blank entry validation),
   routers (admin + league), `dependencies.py` wiring, exception handlers
   in `main.py`.
6. **Tests.** Unit (domain + application + API), integration (migration +
   repository + atomic create-with-seed), e2e (full host-managed flow +
   rule-on rejection + rule-off no-op).

## Related documents

- [eligible_players_ai_agent_guide.md](../../../eligible_players_ai_agent_guide.md) — product brief that motivated this feature.
- [16_league_rules_and_match_policies.md](16_league_rules_and_match_policies.md) — `LeagueRules` versioning pattern; `require_eligible_players` slots into the same JSONB schema and is added under the same "rules immutable after creation" contract.
- [05_aggregate_designs/league.md](05_aggregate_designs/league.md) — League aggregate contract; updated in parallel with this doc to add the `EligiblePlayer` entity.
- [13_api_contracts.md](13_api_contracts.md) — endpoint catalog; updated in parallel with this doc to add the three new endpoints.
- `eligible_players_chat_intents_context.md` (repo root) — proposed chat-intent surface for a follow-up iteration.
- `eligible_players_frontend_context.md` (repo root) — proposed UI surface for a follow-up iteration.
