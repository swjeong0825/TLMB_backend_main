from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.application.use_cases.submit_match_result_use_case import SubmitMatchResultResult
from app.application.use_cases.submit_singles_match_result_use_case import SubmitSinglesMatchResultResult
from app.domain.exceptions import InvalidPlannedMatchError, PlannedMatchMismatchError, PlannedMatchNotFoundError


@pytest.fixture(params=["singles", "doubles"])
def recording_api(request, mock_submit_match_uc, mock_submit_singles_match_uc):
    if request.param == "singles":
        mock = mock_submit_singles_match_uc
        mock.execute.return_value = SubmitSinglesMatchResultResult(str(uuid4()), datetime.now(timezone.utc))
        endpoint = "singles-matches"
        payload = {"player1_nickname": "Alice", "player2_nickname": "Bob", "player1_score": "6", "player2_score": "0"}
    else:
        mock = mock_submit_match_uc
        mock.execute.return_value = SubmitMatchResultResult(str(uuid4()), datetime.now(timezone.utc))
        endpoint = "matches"
        payload = {"pair1_nicknames": ["Alice", "Bob"], "pair2_nicknames": ["Charlie", "Diana"], "pair1_score": "6", "pair2_score": "0"}
    return f"/leagues/{uuid4()}/{endpoint}", payload, mock


@pytest.mark.parametrize("mode", ["omitted", "null", "uuid"])
async def test_optional_uuid_is_forwarded_with_unchanged_response(client, recording_api, mode):
    url, payload, mock = recording_api
    if mode != "omitted":
        payload["planned_match_id"] = str(uuid4()) if mode == "uuid" else None
    response = await client.post(url, json=payload)
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"match_id", "created_at"}
    command = mock.execute.call_args.args[0]
    assert command.planned_match_id == (UUID(payload["planned_match_id"]) if mode == "uuid" else None)


@pytest.mark.parametrize("invalid_id", ["", "not-a-uuid", 1, [], {}])
async def test_invalid_uuid_is_422_before_use_case(client, recording_api, invalid_id):
    url, payload, mock = recording_api
    response = await client.post(url, json={**payload, "planned_match_id": invalid_id})
    assert response.status_code == 422
    mock.execute.assert_not_called()


@pytest.mark.parametrize("field_kind", ["names", "score"])
async def test_planned_id_does_not_make_current_fields_optional(client, recording_api, field_kind):
    url, payload, mock = recording_api
    key = next(key for key in payload if ("nickname" in key if field_kind == "names" else "score" in key))
    del payload[key]
    response = await client.post(url, json={**payload, "planned_match_id": str(uuid4())})
    assert response.status_code == 422
    mock.execute.assert_not_called()


@pytest.mark.parametrize("error,status", [
    (PlannedMatchNotFoundError, 404), (PlannedMatchMismatchError, 409), (InvalidPlannedMatchError, 422),
])
async def test_planned_error_envelope(client, recording_api, error, status):
    url, payload, mock = recording_api
    mock.execute.side_effect = error("planned result rejected")
    response = await client.post(url, json={**payload, "planned_match_id": str(uuid4())})
    assert response.status_code == status
    assert response.json() == {"error": error.__name__, "detail": "planned result rejected"}
