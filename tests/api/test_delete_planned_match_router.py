from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.dependencies import get_delete_planned_match_use_case
from app.domain.exceptions import LeagueNotFoundError, PlannedMatchNotFoundError
from app.main import app


@pytest.fixture
def deletion_use_case():
    use_case = AsyncMock()
    app.dependency_overrides[get_delete_planned_match_use_case] = lambda: use_case
    yield use_case
    app.dependency_overrides.pop(get_delete_planned_match_use_case, None)


async def test_anonymous_delete_returns_empty_204(client, deletion_use_case):
    league_id, plan_id = uuid4(), uuid4()
    response = await client.delete(f'/leagues/{league_id}/planned-matches/{str(plan_id).upper()}')
    assert response.status_code == 204
    assert response.content == b''
    command = deletion_use_case.execute.call_args.args[0]
    assert command.league_id == str(league_id)
    assert command.planned_match_id == plan_id
    assert isinstance(command.planned_match_id, UUID)


@pytest.mark.parametrize('bad_league', [True, False])
async def test_invalid_uuid_rejected_before_use_case(client, deletion_use_case, bad_league):
    league_id = 'bad' if bad_league else str(uuid4())
    plan_id = str(uuid4()) if bad_league else 'bad'
    response = await client.delete(f'/leagues/{league_id}/planned-matches/{plan_id}')
    assert response.status_code == 422
    deletion_use_case.execute.assert_not_called()


@pytest.mark.parametrize('error', [LeagueNotFoundError, PlannedMatchNotFoundError])
async def test_missing_resource_error_envelope(client, deletion_use_case, error):
    deletion_use_case.execute.side_effect = error('missing')
    response = await client.delete(f'/leagues/{uuid4()}/planned-matches/{uuid4()}')
    assert response.status_code == 404
    assert response.json() == {'error': error.__name__, 'detail': 'missing'}


def test_openapi_publishes_delete_with_uuid_parameters_and_no_body():
    operation = app.openapi()['paths']['/leagues/{league_id}/planned-matches/{planned_match_id}']['delete']
    assert 'requestBody' not in operation
    assert not operation.get('security')
    assert 'content' not in operation['responses']['204']
    assert {parameter['name']: parameter['schema']['format'] for parameter in operation['parameters']} == {
        'league_id': 'uuid', 'planned_match_id': 'uuid',
    }


async def test_frontend_origin_allows_delete_preflight(client):
    response = await client.options(f'/leagues/{uuid4()}/planned-matches/{uuid4()}', headers={
        'Origin': 'https://tlmb.swjapps.com', 'Access-Control-Request-Method': 'DELETE',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == 'https://tlmb.swjapps.com'
    assert 'DELETE' in response.headers['access-control-allow-methods']
