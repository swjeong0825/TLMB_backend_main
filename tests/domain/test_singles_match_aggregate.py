from __future__ import annotations

import pytest

from app.domain.aggregates.league.value_objects import LeagueId, PlayerId
from app.domain.aggregates.match.value_objects import SetScore
from app.domain.aggregates.singles_match.aggregate_root import SinglesMatch
from app.domain.exceptions import SamePlayerOnBothSidesError


def test_create_rejects_same_player_on_both_sides() -> None:
    league_id = LeagueId.generate()
    player_id = PlayerId.generate()

    with pytest.raises(SamePlayerOnBothSidesError):
        SinglesMatch.create(
            league_id,
            player_id,
            player_id,
            SetScore("6", "3"),
        )


def test_edit_score_replaces_set_score() -> None:
    match = SinglesMatch.create(
        LeagueId.generate(),
        PlayerId.generate(),
        PlayerId.generate(),
        SetScore("6", "3"),
    )

    match.edit_score(SetScore("4", "6"))

    assert match.set_score.pair1_score == "4"
    assert match.set_score.pair2_score == "6"
