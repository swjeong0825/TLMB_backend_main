"""Planned consumption uses the existing recording transaction in both formats."""
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand, SubmitMatchResultUseCase,
)
from app.application.use_cases.submit_singles_match_result_use_case import (
    SubmitSinglesMatchResultCommand, SubmitSinglesMatchResultUseCase,
)
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.exceptions import (
    InvalidSetScoreError, LeagueNotFoundError, PlannedMatchNotFoundError,
)
from tests.application.conftest import make_league


@pytest.fixture(params=["singles", "doubles"])
def recording(request):
    league = make_league()
    uow = AsyncMock()
    uow.__aenter__.return_value = uow
    uow.league_repo.get_by_id_with_lock.return_value = league
    is_singles = request.param == "singles"
    if is_singles:
        command = SubmitSinglesMatchResultCommand(str(league.league_id), "Alice", "Bob", "6", "0", uuid4())
        use_case = SubmitSinglesMatchResultUseCase(Mock(return_value=uow))
        repo = uow.singles_match_repo
        repo.exists_match_for_player_matchup.return_value = False
        repo.exists_match_for_player_matchup_between.return_value = False
        value = "Alice Bob"
    else:
        command = SubmitMatchResultCommand(str(league.league_id), ("Alice", "Bob"), ("Charlie", "Diana"), "6", "0", uuid4())
        use_case = SubmitMatchResultUseCase(Mock(return_value=uow))
        repo = uow.match_repo
        repo.exists_match_for_pair_matchup.return_value = False
        repo.exists_match_for_pair_matchup_between.return_value = False
        value = "Alice,Bob Charlie,Diana"
    plan = PlannedMatch.create(league.league_id, command.planned_match_id, value)
    uow.planned_match_repo.get_by_id_with_lock.return_value = plan
    return use_case, command, uow, repo, league


async def test_records_deletes_and_commits_in_order(recording):
    use_case, command, uow, repo, league = recording
    result = await use_case.execute(command)
    assert result.match_id
    repo.save.assert_awaited_once()
    uow.planned_match_repo.get_by_id_with_lock.assert_awaited_once_with(league.league_id, command.planned_match_id)
    uow.planned_match_repo.delete.assert_awaited_once_with(league.league_id, command.planned_match_id)
    uow.commit.assert_awaited_once()
    calls = [call[0] for call in uow.mock_calls]
    result_save = "singles_match_repo.save" if isinstance(command, SubmitSinglesMatchResultCommand) else "match_repo.save"
    assert calls.index("league_repo.get_by_id_with_lock") < calls.index("planned_match_repo.get_by_id_with_lock")
    assert calls.index(result_save) < calls.index("planned_match_repo.delete") < calls.index("commit")


async def test_manual_recording_never_reads_or_deletes_plans(recording):
    use_case, command, uow, _, _ = recording
    command.planned_match_id = None
    await use_case.execute(command)
    uow.planned_match_repo.get_by_id_with_lock.assert_not_called()
    uow.planned_match_repo.delete.assert_not_called()


async def test_missing_league_does_not_look_up_plan(recording):
    use_case, command, uow, repo, _ = recording
    uow.league_repo.get_by_id_with_lock.return_value = None
    with pytest.raises(LeagueNotFoundError):
        await use_case.execute(command)
    uow.planned_match_repo.get_by_id_with_lock.assert_not_called()
    repo.save.assert_not_called()
    uow.commit.assert_not_called()


async def test_missing_plan_is_checked_before_score_and_writes(recording):
    use_case, command, uow, repo, _ = recording
    if isinstance(command, SubmitSinglesMatchResultCommand):
        command.player1_score = "invalid"
    else:
        command.pair1_score = "invalid"
    uow.planned_match_repo.get_by_id_with_lock.return_value = None
    with pytest.raises(PlannedMatchNotFoundError):
        await use_case.execute(command)
    repo.save.assert_not_called()
    uow.league_repo.save.assert_not_called()
    uow.planned_match_repo.delete.assert_not_called()
    uow.commit.assert_not_called()


async def test_invalid_score_does_not_consume_plan(recording):
    use_case, command, uow, repo, _ = recording
    if isinstance(command, SubmitSinglesMatchResultCommand):
        command.player1_score = "-1"
    else:
        command.pair1_score = "-1"
    with pytest.raises(InvalidSetScoreError):
        await use_case.execute(command)
    repo.save.assert_not_called()
    uow.planned_match_repo.delete.assert_not_called()
    uow.commit.assert_not_called()


@pytest.mark.parametrize("failure_at", ["save", "delete", "commit"])
async def test_storage_errors_escape_transaction_without_success(recording, failure_at):
    use_case, command, uow, repo, _ = recording
    operation = {"save": repo.save, "delete": uow.planned_match_repo.delete, "commit": uow.commit}[failure_at]
    operation.side_effect = RuntimeError("storage failure")
    with pytest.raises(RuntimeError, match="storage failure"):
        await use_case.execute(command)
    assert uow.__aexit__.call_args.args[0] is RuntimeError
    if failure_at != "commit":
        uow.commit.assert_not_called()
