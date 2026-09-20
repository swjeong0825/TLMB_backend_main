# Connect the planned-match recording UI to Backend Main

The backend now accepts an optional `planned_match_id` on its existing singles and
doubles result APIs. One successful request records the result and hard-deletes the
selected pending plan in the same transaction. Participant names and both scores
remain required.

This guide describes the implemented backend contract and the frontend work needed
to connect the current stub. It supersedes the separate recording endpoint and
receipt/retry behavior proposed in the frontend's
`docs/record-planned-match-api-request.md`. Deployment must include this backend
change before enabling the frontend path; live deployment is not verified here.
No migration beyond the existing planned-match migration `015` is needed.

## 1. Connection and endpoint selection

Send requests directly to **Backend Main**, using the frontend's existing
`TLCHAT_CHAT.backendMainBase()`. Chat-to-Intent is not involved in recording or
refreshing the resulting match history.

| Operation | Method and path | Success |
|---|---|---|
| Load pending plans | `GET /leagues/{league_id}/planned-matches` | 200, `{ "matches": [{ "id": "uuid", "value": "…" }] }` |
| Record a singles plan | `POST /leagues/{league_id}/singles-matches` | 201, `{ "match_id": "uuid", "created_at": "…" }` |
| Record a doubles plan | `POST /leagues/{league_id}/matches` | 201, `{ "match_id": "uuid", "created_at": "…" }` |

Use `Content-Type: application/json`, `Accept: application/json`, and
`credentials: "omit"`. No `X-Host-Token` or authorization header is required.
Both recording routes retain the existing 30 requests/minute limit when rate
limiting is enabled. Encode the league ID when constructing the URL and use the
configured base URL, rather than a hardcoded deployment address.

There is no `/planned-matches/{id}/record` route or standalone plan-delete route.
Do not send a result POST followed by a DELETE, and do not call the frontend's
`TLCHAT_PLAN.deleteMatch` stub after recording.

## 2. Build a result from the selected saved plan

Keep the `{id, value}` returned by GET with the score form. Use the saved ID, not a
new UUID. Parse that same saved value to determine the endpoint and participants:

| Saved `value` | Format | Side 1 | Side 2 |
|---|---|---|---|
| `Alice Bob` | singles | Alice | Bob |
| `Alice,Bob Charlie,Diana` | doubles | Alice + Bob | Charlie + Diana |

`TLCHAT_PLAN.parseValue(value)` already returns `{format, sides}`. Preserve side
order: the first displayed score belongs to `sides[0]`, the second to `sides[1]`.
Keep participant names fixed in this flow. Korean names and existing aliases may
be sent exactly as they appear in the plan.

### Singles example

Given `{ "id": "719e28b2-bce7-4e48-92a7-204711504dc8", "value": "Alice Bob" }`,
send `POST /leagues/{league_id}/singles-matches`:

```json
{
  "player1_nickname": "Alice",
  "player2_nickname": "Bob",
  "player1_score": "6",
  "player2_score": "0",
  "planned_match_id": "719e28b2-bce7-4e48-92a7-204711504dc8"
}
```

### Doubles example

Given `{ "id": "15b4d9c8-6ba0-4de8-909e-9f55b7932d0a", "value": "Alice,Bob Charlie,Diana" }`,
send `POST /leagues/{league_id}/matches`:

```json
{
  "pair1_nicknames": ["Alice", "Bob"],
  "pair2_nicknames": ["Charlie", "Diana"],
  "pair1_score": "6",
  "pair2_score": "3",
  "planned_match_id": "15b4d9c8-6ba0-4de8-909e-9f55b7932d0a"
}
```

Scores must be **JSON strings**, including `"0"`. Missing scores, empty strings,
negative scores, and non-integer scores are invalid. The backend accepts
non-negative integers and permits draws; the current frontend's 0–21 selector is a
UI restriction, not a new backend limit.

Omitting `planned_match_id` or passing null records a manual result and leaves
plans untouched. The planned flow must always include its saved UUID. Never retry
a failed planned submission by dropping the ID.

### Mapping example for the existing stub

Inside the existing `js/plan/record.js` IIFE, `api` is `TLCHAT_PLAN` and `score()` is
its current score-validation helper. Replace the old `recordPayload` mapping with:

```javascript
function recordPayload(record, side1Score, side2Score) {
  if (!api.isValidRecord(record)) throw new Error("plannedLoadFailed");
  var parsed = api.parseValue(record.value);
  var firstScore = score(side1Score);
  var secondScore = score(side2Score);

  if (parsed.format === "singles") {
    return {
      player1_nickname: parsed.sides[0][0],
      player2_nickname: parsed.sides[1][0],
      player1_score: firstScore,
      player2_score: secondScore,
      planned_match_id: record.id,
    };
  }
  return {
    pair1_nicknames: parsed.sides[0].slice(),
    pair2_nicknames: parsed.sides[1].slice(),
    pair1_score: firstScore,
    pair2_score: secondScore,
    planned_match_id: record.id,
  };
}
```

In `recordMatch(leagueId, record, side1Score, side2Score)`, validate the record/build
the body first. Select `singles-matches` or `matches` from `parseValue(record.value).format`,
then POST `JSON.stringify(body)` to:

```text
backendMainBase().replace(/\/+$/, "") + "/leagues/" + encodeURIComponent(leagueId) + "/" + endpoint
```

Keep the existing 30-second `AbortController` pattern from `js/plan/api.js` and
always clear its timer in `finally`. An abort stops the browser's wait; it does not
prove the backend transaction was cancelled.

The old `expected_value`, `side1_score`, and `side2_score` fields are **not the wire
contract**. Do not send them or a separate `match_format` field. The backend checks
the supplied participant names against the saved plan rather than comparing an
`expected_value` string byte-for-byte.

## 3. What the backend checks

The backend locks the league, then finds and locks the plan using both the league
ID and planned-match ID. A plan ID belonging only to another league is not found.
It checks the endpoint's format and compares names on each side after the existing
nickname trimming and lowercase normalization.

- Case and surrounding allowed whitespace do not affect name equality.
- Doubles teammate order may differ within the same side.
- Side 1 and side 2 cannot be exchanged to match the plan.
- A different alias for the same player is not accepted as a replacement planned
  name. For a plan containing `Ace`, send `Ace`; normal alias resolution happens
  after this comparison.
- The comparison does not overwrite or normalize the saved plan.

After those checks, all existing recording rules apply: score validation,
repeated-player checks, roster restrictions, allowed automatic registration,
pair membership, and rematch policy. A valid plan can therefore still be rejected
at recording time. Planning allows unknown/repeated names; recording may not.

One transaction saves the result and any permitted roster/pair/activity changes,
hard-deletes the plan, and commits before returning success. A validation failure
or rolled-back transaction does not consume the plan or leave partial result data.

## 4. Success response and UI changes

Successful singles and doubles recordings both return **HTTP 201**:

```json
{
  "match_id": "3e846a0f-6ef1-42f6-971b-45e2fa920697",
  "created_at": "2026-09-20T12:34:56.123456Z"
}
```

`match_id` is the newly recorded result's ID; it is not the planned ID.
`created_at` is the server timestamp. The response does not include
`planned_match_id`, `match_format`, or a list of remaining plans. Retain the
submitted ID and format in the request context.

The frontend adapter can return this local result shape (not a backend envelope):

- Confirmed success: `{ ok: true, match_id, created_at }`.
- Failure: `{ ok: false, error, status, code, detail, unconfirmed }`, where `error`
  is a frontend translation key, `code` is the backend error name when present,
  and unavailable fields may be omitted.

Validate the successful response shape before reporting confirmed success. Treat a
201 with an unreadable/malformed body as unconfirmed and reconcile using GET.

Update `js/chat/planned-match-interactions.js` as well as the adapter. Its current
submit handler always renders `tr(result.error)` and has no success branch.

1. Guard against duplicate submission for the selected row, disable its submit
   button while pending, and preserve the selected plan and score draft.
2. Await `recordMatch`, then check `result.ok` before reading `result.error`.
3. On confirmed success, remove the submitted row and its score draft and show
   confirmation. Refresh saved plans with `TLCHAT_PLAN.loadMatches(leagueId)`.
4. Refresh visible history and standings directly from Backend Main. History uses
   `GET /leagues/{id}/matches?scope=both` (or the view's selected scope); standings
   use `GET /leagues/{id}/standings?scope=singles|doubles|both`. Refresh roster data
   if shown, since recording can register players/pairs and update activity dates.
5. A failed refresh after confirmed recording is a refresh error, not a recording
   failure. Do not POST the result again because a follow-up GET failed.
6. On rejection, retain entered scores where still applicable, show a useful
   message, and re-enable submission after addressing the error. After any await,
   check that the panel/form still belongs to the active view before updating it.

Remove/replace the `plannedStubHint` message when enabling this path. Add localized
success, missing-plan, mismatch, rejected, rate-limited, and unconfirmed-result
messages; the current `plannedRecordUnavailable` fallback alone is insufficient.
When refreshing, keep drafts only for the same ID **and unchanged saved value**,
as the current loader already does. Scores from a changed matchup must not be
silently reused for the new matchup.

## 5. Errors and recovery

Domain errors use this envelope:

```json
{
  "error": "PlannedMatchMismatchError",
  "detail": "Submitted participants do not match the planned sides"
}
```

Read both HTTP status and `error`; status alone cannot distinguish a missing
league from a missing plan, or a changed plan from a rematch restriction.

| Status / code | Meaning | Frontend action |
|---|---|---|
| 404 `LeagueNotFoundError` | League does not exist. | Show the league-unavailable message and stop submission. |
| 404 `PlannedMatchNotFoundError` | Plan is absent in this league, including after consumption. | Refresh plans and history. Explain that the plan is no longer pending; do not claim this request recorded it. |
| 409 `PlannedMatchMismatchError` | Saved sides differ from submitted names. | Reload the plan and require the user to review its participants and scores before submitting again. |
| 422 `InvalidPlannedMatchError` | Plan format differs from the selected endpoint, or stored plan grammar is invalid. | Refresh; rebuild from the saved format. Do not fall back to manual recording. |
| 422 request validation | Invalid UUID, missing fields, incorrect field types, or malformed name arrays. | Correct request construction/input. |
| 422 `InvalidPlayerNicknameError`, `InvalidSetScoreError` | Invalid nickname or score. | Show the relevant validation message and retain the draft. |
| 422 `SamePlayerWithinSinglePairError`, `SamePlayerOnBothPairsError`, `SamePlayerOnBothSidesError` | The actual result would repeat a player illegally. | Explain the participant issue; the plan remains pending. |
| 422 `RosterMembershipRequiredError` | Closed-roster league has unregistered participants. | Show `missing_nicknames` when provided; arrange registration/correction before retrying. |
| 409 `PairConflictError`, `SamePairOnBothSidesError` | Existing pair/participant rules reject the result. | Show the rule conflict; do not retry automatically. |
| 409 `DuplicatePairMatchupMatchError`, `DuplicateSinglesMatchupMatchError` | Rematch policy rejects another result. | Refresh history and explain the existing-match restriction. |
| 429 | Rate limit exceeded. | Ask the user to wait; avoid repeated submissions. |
| 5xx, timeout, network error, or unreadable success body | Outcome may be unconfirmed from the browser. | Preserve the draft and reconcile plans/history before retrying. |

FastAPI request-validation errors instead use `{ "detail": [ ... ] }`, with entries
such as `loc`, `msg`, and `type`. Do not assume `error` always exists or that `detail`
is always a string. Rate-limit/proxy errors may use another shape or non-JSON bodies;
handle response parsing failures and provide a fallback message. Render details as
text, not HTML.

### Retries and uncertain outcomes

There is no consumption receipt or automatic success replay. Once a pending plan
is successfully consumed, another recording POST for that ID returns **404**.
Concurrent submissions for the same pending plan yield one result; the later
request finds the plan missing.

After an uncertain response, reload pending plans and match history. If the plan
is absent, do not recreate it or submit manually: another request may have already
recorded it. Absence alone cannot recover the result ID or prove which request
succeeded. If the plan remains, let the user review the refreshed matchup and
history before explicitly retrying with the same planned ID.

A later upload can recreate a consumed UUID, including an upload already queued
behind recording. The backend does not permanently reserve consumed IDs. Do not
reuse the upload adapter's automatic-retry assumptions for recording, and do not
automatically re-upload stale saved plans as part of error recovery.

## 6. Frontend acceptance checklist

- Singles and doubles select the correct route and exact field names; scores are
  strings, zero works, and the saved plan ID is always included.
- Successful recording shows confirmation, removes the pending row, and refreshes
  result data without issuing a second delete request.
- Manual recording still omits the ID or passes null and leaves plans untouched.
- Double-clicking submit issues at most one in-flight request per row.
- Changed names/sides, missing plans, closed rosters, invalid scores, pair conflicts,
  and rematch errors show distinct useful messages and preserve appropriate drafts.
- Timeout/lost-response handling refreshes state without automatic re-recording or
  re-upload. A post-success refresh failure never resubmits the result.
- Refreshing or navigating away while a POST is pending cannot update a detached
  form, resurrect a consumed row from stale local state, or assign old scores to a
  changed plan. Always reconcile against the latest GET after completion.

Backend references: [API contracts](../Design_Doc/TLMB_Design_doc/13_api_contracts.md#planned-consumption-on-result-submission),
[planned-match design](../Design_Doc/TLMB_Design_doc/23_planned_matches.md), and
[recording E2E tests](../tests/e2e/test_record_planned_matches.py).
