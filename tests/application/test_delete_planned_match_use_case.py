from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.application.use_cases.delete_planned_match_use_case import DeletePlannedMatchCommand, DeletePlannedMatchUseCase
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.exceptions import LeagueNotFoundError, PlannedMatchNotFoundError


@pytest.fixture
def deletion():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.league_repo.lock_by_id.return_value = True
    command = DeletePlannedMatchCommand(str(uuid4()), uuid4())
    return DeletePlannedMatchUseCase(Mock(return_value=uow)), command, uow


async def test_deletes_scoped_plan_and_commits_without_loading_roster(deletion):
    use_case, command, uow = deletion
    assert await use_case.execute(command) is None
    league_id = LeagueId.from_str(command.league_id)
    uow.league_repo.lock_by_id.assert_awaited_once_with(league_id)
    uow.planned_match_repo.delete.assert_awaited_once_with(league_id, command.planned_match_id)
    uow.commit.assert_awaited_once()
    calls = [call[0] for call in uow.mock_calls]
    assert calls.index('league_repo.lock_by_id') < calls.index('planned_match_repo.delete') < calls.index('commit')
    uow.league_repo.get_by_id.assert_not_called()
    uow.league_repo.get_by_id_with_lock.assert_not_called()
    uow.league_repo.save.assert_not_called()
    uow.planned_match_repo.get_by_id_with_lock.assert_not_called()


async def test_missing_league_does_not_delete_or_commit(deletion):
    use_case, command, uow = deletion
    uow.league_repo.lock_by_id.return_value = False
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(command)
    uow.planned_match_repo.delete.assert_not_called()
    uow.commit.assert_not_called()


async def test_missing_plan_does_not_commit(deletion):
    use_case, command, uow = deletion
    uow.planned_match_repo.delete.side_effect = PlannedMatchNotFoundError('missing')
    with pytest.raises(PlannedMatchNotFoundError):
        await use_case.execute(command)
    uow.commit.assert_not_called()


@pytest.mark.parametrize('failure_at', ['delete', 'commit'])
async def test_failure_leaves_transaction_without_success(deletion, failure_at):
    use_case, command, uow = deletion
    operation = uow.commit if failure_at == 'commit' else uow.planned_match_repo.delete
    operation.side_effect = RuntimeError('storage failed')
    with pytest.raises(RuntimeError, match='storage failed'):
        await use_case.execute(command)
    assert uow.__aexit__.call_args.args[0] is RuntimeError
    if failure_at == 'delete':
        uow.commit.assert_not_called()
