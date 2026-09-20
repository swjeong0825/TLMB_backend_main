from uuid import uuid4

import pytest

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.aggregates.planned_match.value_objects import PlannedMatchValue
from app.domain.exceptions import InvalidPlannedMatchError, PlannedMatchMismatchError
from app.domain.nicknames import NICKNAME_WHITESPACE


@pytest.mark.parametrize("value", [
    "Alice Bob", "민수 지수", "Alice,Bob Charlie,Diana", "A-1,B_2 C.3,D4",
    "Alice Alice", "Alice,Alice Alice,Alice", "\u0085Alice Bob",
])
def test_preserves_valid_value_and_client_identity(value):
    league_id, id = LeagueId.generate(), uuid4()
    match = PlannedMatch.create(league_id, id, value)
    assert (match.league_id, match.id, match.value.value) == (league_id, id, value)


@pytest.mark.parametrize("value", [
    "", "Alice", " Alice Bob", "Alice Bob ", "Alice  Bob",
    "Alice,Bob Charlie", "Alice Bob,Charlie", "Alice, Bob,Charlie",
    "Alice,,Bob Charlie,Diana", "A,B,C D,E,F", "Alice\tBob", 1, None,
])
def test_rejects_invalid_grammar(value):
    with pytest.raises(InvalidPlannedMatchError):
        PlannedMatchValue(value)


@pytest.mark.parametrize("space", NICKNAME_WHITESPACE)
@pytest.mark.parametrize("template", ["Al{}ice Bob", "{}Alice Bob", "Alice Bob{}"])
def test_rejects_all_javascript_whitespace_inside_or_around_names(space, template):
    with pytest.raises(InvalidPlannedMatchError):
        PlannedMatchValue(template.format(space))


@pytest.mark.parametrize("value,side1,side2", [
    ("Alice Bob", (" ALICE\ufeff",), ("bob",)),
    ("민수 지수", ("민수",), ("지수",)),
    ("Alice,Bob Charlie,Diana", ("BOB", "alice"), ("diana", "charlie")),
    ("Alice,Alice Bob,Bob", ("alice", "ALICE"), ("bob", "BOB")),
])
def test_participant_comparison_preserves_value(value, side1, side2):
    plan = PlannedMatchValue(value)
    plan.validate_participants(side1, side2)
    assert plan.value == value


@pytest.mark.parametrize("value,side1,side2", [
    ("Alice Bob", ("bob",), ("alice",)),
    ("Ace Bob", ("alice",), ("bob",)),
    ("Alice,Bob Charlie,Diana", ("alice", "charlie"), ("bob", "diana")),
    ("Alice,Bob Charlie,Diana", ("charlie", "diana"), ("alice", "bob")),
    ("Alice,Bob Charlie,Diana", ("alice", "alice"), ("charlie", "diana")),
])
def test_different_participants_or_sides_are_a_conflict(value, side1, side2):
    with pytest.raises(PlannedMatchMismatchError):
        PlannedMatchValue(value).validate_participants(side1, side2)


@pytest.mark.parametrize("value,side1,side2", [
    ("Alice Bob", ("alice", "bob"), ("charlie", "diana")),
    ("Alice,Bob Charlie,Diana", ("alice",), ("charlie",)),
])
def test_wrong_result_format_is_invalid(value, side1, side2):
    with pytest.raises(InvalidPlannedMatchError):
        PlannedMatchValue(value).validate_participants(side1, side2)
