from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.application.use_cases.get_planned_matches_use_case import GetPlannedMatchesQuery, GetPlannedMatchesUseCase
from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.application.use_cases.upload_planned_matches_use_case import UploadPlannedMatchesCommand, UploadPlannedMatchesUseCase
from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.exceptions import InvalidPlannedMatchError, LeagueNotFoundError


def upload_setup():
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.league_repo.lock_by_id.return_value = True
    factory = Mock(return_value=uow)
    return UploadPlannedMatchesUseCase(factory), uow, factory


async def test_upload_commits_and_returns_input_order_without_loading_roster():
    use_case, uow, _ = upload_setup()
    records = [PlannedMatchRecord(uuid4(), "민수 지수"), PlannedMatchRecord(uuid4(), "A,A A,A")]
    command = UploadPlannedMatchesCommand(str(uuid4()), records)
    assert await use_case.execute(command) == records
    uow.commit.assert_awaited_once()
    uow.league_repo.get_by_id.assert_not_called()
    uow.league_repo.get_by_id_with_lock.assert_not_called()
    uow.league_repo.save.assert_not_called()
    calls = [call[0] for call in uow.mock_calls]
    assert calls.index("league_repo.lock_by_id") < calls.index("planned_match_repo.upsert_many")
    assert [m.id for m in uow.planned_match_repo.upsert_many.call_args.args[0]] == [m.id for m in records]


@pytest.mark.parametrize("kind", ["empty", "duplicate", "malformed"])
async def test_invalid_batch_never_enters_transaction(kind):
    use_case, uow, factory = upload_setup()
    record = PlannedMatchRecord(uuid4(), "Alice Bob")
    records = {"empty": [], "duplicate": [record, record], "malformed": [record, PlannedMatchRecord(uuid4(), "bad")]}[kind]
    with pytest.raises(InvalidPlannedMatchError):
        await use_case.execute(UploadPlannedMatchesCommand(str(uuid4()), records))
    factory.assert_not_called()
    uow.commit.assert_not_called()


async def test_missing_league_does_not_write():
    use_case, uow, _ = upload_setup()
    uow.league_repo.lock_by_id.return_value = False
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(UploadPlannedMatchesCommand(str(uuid4()), [PlannedMatchRecord(uuid4(), "A B")]))
    uow.planned_match_repo.upsert_many.assert_not_called()
    uow.commit.assert_not_called()


@pytest.mark.parametrize("failure_at", ["upsert", "commit"])
async def test_storage_failure_is_not_returned_as_success(failure_at):
    use_case, uow, _ = upload_setup()
    failing = uow.commit if failure_at == "commit" else uow.planned_match_repo.upsert_many
    failing.side_effect = RuntimeError("storage failed")
    with pytest.raises(RuntimeError, match="storage failed"):
        await use_case.execute(UploadPlannedMatchesCommand(str(uuid4()), [PlannedMatchRecord(uuid4(), "A B")]))
    assert uow.__aexit__.call_args.args[0] is RuntimeError


async def test_list_checks_existence_and_returns_only_id_value():
    league_repo, plans = AsyncMock(), AsyncMock()
    league_id = LeagueId.generate()
    plan = PlannedMatch.create(league_id, uuid4(), "Alice Bob")
    plans.get_all_by_league.return_value = [plan]
    use_case = GetPlannedMatchesUseCase(league_repo, plans)
    assert await use_case.execute(GetPlannedMatchesQuery(str(league_id))) == [PlannedMatchRecord(plan.id, "Alice Bob")]
    league_repo.get_by_id.assert_not_called()
    league_repo.exists.return_value = False
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(GetPlannedMatchesQuery(str(league_id)))
