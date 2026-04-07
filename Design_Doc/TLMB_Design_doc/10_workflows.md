# Workflows

## No Workflows Required in V1

After reviewing all business actions and use cases, **no application workflows are needed for the Tennis League Manager in V1**.

Every business operation in this system is either:
- A single atomic use case (one consistency boundary, one or two repository calls)
- A read-only query (pure projection, no state mutation)

There is no multi-step orchestration that spans multiple use cases and requires a workflow coordinator.

### Why each candidate was ruled out

**SubmitMatchResult + implicit registration** — although this involves two aggregates (League and Match), the entire operation is handled atomically within a single use case (`SubmitMatchResultUseCase`) under one Unit of Work. There is no multi-step sequence that needs to be coordinated across separate use cases.

**Admin operations** — each admin action (edit nickname, delete team, edit score, delete match) is an independent, atomic use case. There is no admin setup or teardown flow that chains multiple operations.

**League setup by host** — creating a league and then submitting the first match are separate, independent user-triggered actions. The system does not require them to be coupled in a workflow; the host simply calls each endpoint independently.

**Standings and read projections** — all read paths are single-use-case queries. No aggregation pipeline or multi-step read coordination is needed.

### When a workflow would be reconsidered

A workflow would become appropriate if a future version introduced:
- A multi-step league setup wizard (create league → invite players → configure settings → activate)
- Bulk match import that requires sequential processing and partial failure handling across many use cases
- A season reset flow (archive matches → reset standings → prepare new season) spanning multiple aggregates
- Any background async processing that chains use cases via events or queues
