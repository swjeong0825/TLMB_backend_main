# Delete a saved planned match: frontend integration

Use this endpoint to remove a pending plan without recording a result:

```http
DELETE /leagues/{league_id}/planned-matches/{planned_match_id}
```

The backend hard-deletes only the matching plan in that league. Players, aliases,
pairs, recorded results, standings, and league activity dates are unchanged. There
is no new table or migration. This guide describes the implemented source contract;
the backend version containing this endpoint must be deployed before enabling it
in the frontend.

## Request and response

| Item | Contract |
|---|---|
| Base URL | Existing `TLCHAT_CHAT.backendMainBase()`; call Backend Main directly. |
| Path parameters | `league_id` and `planned_match_id` must both be UUIDs. Use the saved plan's `id`. |
| Request body | None. No scores, names, `value`, or `expected_value` are required. |
| Authentication | Public league-link access; no host token or authorization header. Use `credentials: "omit"`. |
| Rate limit | 60 requests/minute when rate limiting is enabled, consistent with existing public result-deletion routes. |
| Success | **204 No Content**, with an empty response body. **Do not call `response.json()` on success.** |
| Missing resource | **404** for a missing league or a plan absent in that league. A repeated successful deletion returns 404. |
| Invalid identifiers | **422** with the normal FastAPI validation response. |

This works for singles and doubles plans, including unknown or repeated nicknames.
There is no recording-time roster, pair, rematch, or result-delete-window check.
Deletion addresses the ID only: an intervening edit to that plan's value does not
cause a conflict, and no value-version precondition is accepted.

Example for a saved record
`{"id":"719e28b2-bce7-4e48-92a7-204711504dc8","value":"Alice Bob"}`:

```http
DELETE /leagues/6416e5d8-83cc-428e-9d52-240e1d6d1e08/planned-matches/719e28b2-bce7-4e48-92a7-204711504dc8
Accept: application/json
```

```http
HTTP/1.1 204 No Content
```

Use the league ID currently being viewed. Another league may legitimately have a
plan with the same UUID; deleting one does not delete the other.

## Replace the current frontend stub

The current `js/plan/api.js` exports
`TLCHAT_PLAN.deleteMatch(leagueId, record)`, which always returns
`{ok:false,error:"deleteUnavailable"}`. Its caller in `js/plan.js` currently renders
`result.error` unconditionally, so updating the network adapter alone is insufficient.

The following adapter can replace that stub inside the existing IIFE. `global`
is the same browser global used by the surrounding module. The translation keys
below are frontend keys; add their localized messages before enabling the UI.

```javascript
async function deleteMatch(leagueId, record) {
  var id = record && record.id;
  if (typeof id !== "string" ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) {
    return { ok: false, error: "deleteRejected" };
  }
  var base = global.TLCHAT_CHAT.backendMainBase();
  if (!base || !leagueId) return { ok: false, error: "deleteConfigError" };

  var controller = new AbortController();
  var timer = setTimeout(function () { controller.abort(); }, 30000);
  try {
    var response = await fetch(
      base.replace(/\/+$/, "") + "/leagues/" + encodeURIComponent(leagueId) +
      "/planned-matches/" + encodeURIComponent(id),
      { method: "DELETE", credentials: "omit",
        headers: { Accept: "application/json" }, signal: controller.signal }
    );
    if (response.status === 204) return { ok: true };

    var data;
    try { data = await response.json(); } catch (_err) { data = null; }
    var code = data && typeof data.error === "string" ? data.error : "";
    var unconfirmed = response.status >= 500 || response.ok;
    var error = unconfirmed ? "deleteUnconfirmed" :
      code === "LeagueNotFoundError" ? "deleteLeagueMissing" :
      code === "PlannedMatchNotFoundError" ? "deletePlanMissing" :
      response.status === 404 || response.status === 405 ? "deleteUnavailable" :
      response.status === 422 ? "deleteRejected" :
      response.status === 429 ? "deleteRateLimited" : "deleteFailed";
    return { ok: false, error: error, status: response.status, code: code,
      unconfirmed: unconfirmed,
      detail: data && typeof data.detail === "string" ? data.detail : "" };
  } catch (_err) {
    return { ok: false, error: "deleteUnconfirmed", unconfirmed: true };
  } finally {
    clearTimeout(timer);
  }
}
```

Keep `api.deleteMatch = deleteMatch`. This function returns a local frontend result
object; `{ok:true}` is not a JSON response sent by the backend. Validate the saved
ID rather than requiring its value to parse: the delete API can also remove a row
whose stored value is malformed.

## Update saved-plan state and UI

Route deletion through a new `deleteSaved(record)` operation on
`createPlanManager` in `js/plan/controller.js`, following its existing write lifecycle:

1. Capture the selected record's ID and reject another write while one is pending.
2. Increment `readVersion`, clear the active loading state, and set `writing` to
   `"delete"` before sending the request. This invalidates GET requests that started
   before deletion and prevents them from restoring a stale row.
3. Await `api.deleteMatch(options.leagueId, record)`. Ignore completion if the
   manager has been disposed. Always clear the writing state for an active manager.
4. On `result.ok`, filter the saved list by the captured ID, comparing UUID text
   case-insensitively. Notify/render state and show a deletion-success message.
   Use IDs to update state, not a list index retained across an await.
5. Refresh with `loadSaved()` after clearing the write state. A refresh failure
   after confirmed 204 is a refresh error; it must not turn deletion into a failed
   write or automatically repeat DELETE.
6. Preserve unrelated drafts. Close an editor for the deleted saved item and avoid
   automatically uploading stale copies of that ID.

Update the `[data-saved-delete]` click handler in `js/plan.js` to call the manager
operation, inspect `result.ok`, and use a success translation instead of always
rendering `result.error`. Disable the relevant controls while the write is pending
and check that the page/status element is still active before touching the DOM.

On errors, show the appropriate message and reconcile the list as described below.
Standalone plan deletion does not require a standings refresh because it changes
no results. If the plan disappeared because someone recorded it concurrently,
refresh visible match history/standings as part of reconciling that situation.

## Errors, retries, and concurrent changes

Domain errors use the existing envelope, for example:

```json
{
  "error": "PlannedMatchNotFoundError",
  "detail": "Planned match '719e28b2-bce7-4e48-92a7-204711504dc8' not found in this league"
}
```

| Response | Frontend handling |
|---|---|
| 404 `LeagueNotFoundError` | Show league unavailable; do not claim deletion succeeded. |
| 404 `PlannedMatchNotFoundError` | The plan is already absent in this league. Refresh the list and explain it may have been deleted or recorded elsewhere. The desired absent state can be reconciled without another write. |
| 404 without that domain code, or 405 | Could indicate the wrong URL or a backend version without this route. Do not interpret every 404 as successful deletion; verify deployment and endpoint selection. |
| 422 | Correct malformed path identifiers. Request-validation errors contain a `detail` array, not necessarily an `error` string. |
| 429 | Wait and let the user retry; avoid repeated requests. |
| 5xx or network/timeout error | Show an unconfirmed outcome and refresh before offering another explicit attempt. |

A failed database transaction rolls back the deletion. A browser timeout or lost
response does not prove failure: the server may already have committed. Keep the
row until success or a fresh GET establishes its current state; do not automatically
re-upload it to undo an uncertain deletion. Render error details as text, not HTML.

Uploads, result recording, and standalone deletion use the same league-before-plan
lock order. If deletion wins a race with recording, recording returns 404 and creates
no result. If recording wins, deletion returns 404 and the recorded result remains.
Concurrent deletes yield one 204 and a subsequent 404.

Deletion creates no tombstone. A later upload, including one already queued behind
the DELETE, can recreate the same UUID. Refresh after completion to show the current
server state. Deleting a plan does not delete an already recorded result.

When recording a planned match, continue using the result POST with
`planned_match_id`; that transaction already removes the plan. Do **not** use this
DELETE before or after that POST as part of the recording flow. See the
[recording integration guide](planned-match-recording-frontend-guide.md).

## Deployment check and frontend acceptance

The selected backend's `GET /openapi.json` should contain a `delete` operation at:

```text
paths["/leagues/{league_id}/planned-matches/{planned_match_id}"].delete
```

This read-only check verifies the route is advertised. A generic 404 from an older
backend is not proof that a plan is absent. Do not hardcode the production URL when
checking support; use the same configured backend base as the DELETE request.

Verify with an isolated test league after deployment:

- Both singles and doubles plans delete anonymously, returning an empty 204 body.
- The row disappears from GET, while other plans and recorded league data remain.
- Invalid IDs give 422; missing leagues/plans give distinguishable 404 errors.
- A 204 is handled without JSON parsing, and a second DELETE receives 404.
- Success removes the saved row; failed/uncertain requests reconcile rather than
  blindly removing or recreating it. A post-success GET failure never repeats DELETE.
- Double-clicks, stale GET responses, in-flight uploads, navigation, and disposed
  views do not corrupt frontend state.

Backend references: [API contracts](../Design_Doc/TLMB_Design_doc/13_api_contracts.md#endpoint-delete-planned-match),
[planned-match design](../Design_Doc/TLMB_Design_doc/23_planned_matches.md), and
[deletion E2E tests](../tests/e2e/test_delete_planned_matches.py).
