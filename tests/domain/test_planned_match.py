from uuid import uuid4

import pytest

from app.domain.aggregates.league.value_objects import LeagueId
from app.domain.aggregates.planned_match.aggregate_root import PlannedMatch
from app.domain.aggregates.planned_match.value_objects import PlannedMatchValue
from app.domain.exceptions import InvalidPlannedMatchError
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
