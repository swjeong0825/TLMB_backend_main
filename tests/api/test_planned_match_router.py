from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.dependencies import get_get_planned_matches_use_case, get_upload_planned_matches_use_case
from app.domain.exceptions import InvalidPlannedMatchError, LeagueNotFoundError
from app.main import app


@pytest.fixture
def plans_use_case():
    use_case = AsyncMock()
    use_case.execute.side_effect = lambda command: getattr(command, "matches", [])
    app.dependency_overrides[get_upload_planned_matches_use_case] = lambda: use_case
    app.dependency_overrides[get_get_planned_matches_use_case] = lambda: use_case
    yield use_case
    app.dependency_overrides.pop(get_upload_planned_matches_use_case, None)
    app.dependency_overrides.pop(get_get_planned_matches_use_case, None)


async def test_anonymous_upload_and_empty_read(client, plans_use_case):
    url = f"/leagues/{uuid4()}/planned-matches"
    body = {"matches": [{"id": str(uuid4()), "value": "Alice,Bob 민수,지수"}]}
    response = await client.post(url, json=body)
    assert response.status_code == 200
    assert response.json() == body
    response = await client.get(url)
    assert response.status_code == 200
    assert response.json() == {"matches": []}


@pytest.mark.parametrize("body", [
    {}, {"matches": []}, {"matches": None}, {"matches": "bad"}, [],
    {"matches": [None]}, {"matches": [{}]},
    {"matches": [{"id": "bad", "value": "A B"}]},
    {"matches": [{"id": str(uuid4()), "value": 12}]},
    {"matches": [{"id": str(uuid4()), "value": None}]},
    {"matches": [{"id": str(uuid4()), "value": "A  B"}]},
    {"matches": [{"id": str(uuid4()), "value": "A B", "format": "singles"}]},
])
async def test_invalid_request_never_calls_use_case(client, plans_use_case, body):
    response = await client.post(f"/leagues/{uuid4()}/planned-matches", json=body)
    assert response.status_code == 422, response.text
    plans_use_case.execute.assert_not_called()


async def test_duplicate_uuid_identity_and_invalid_league_uuid(client, plans_use_case):
    id = str(uuid4())
    body = {"matches": [{"id": id, "value": "A B"}, {"id": id.upper(), "value": "C D"}]}
    assert (await client.post(f"/leagues/{uuid4()}/planned-matches", json=body)).status_code == 422
    assert (await client.get("/leagues/bad/planned-matches")).status_code == 422
    assert (await client.post("/leagues/bad/planned-matches", json={"matches": [body["matches"][0]]})).status_code == 422
    plans_use_case.execute.assert_not_called()


@pytest.mark.parametrize("error,status", [(LeagueNotFoundError("missing"), 404), (InvalidPlannedMatchError("bad"), 422)])
async def test_domain_error_envelope(client, plans_use_case, error, status):
    plans_use_case.execute.side_effect = error
    response = await client.post(f"/leagues/{uuid4()}/planned-matches", json={"matches": [{"id": str(uuid4()), "value": "A B"}]})
    assert response.status_code == status
    assert response.json() == {"error": type(error).__name__, "detail": str(error)}
