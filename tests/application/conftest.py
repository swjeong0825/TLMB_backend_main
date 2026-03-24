"""Shared fixtures for application-layer unit tests.

All repositories are in-memory mocks; no database is required.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.domain.aggregates.league.aggregate_root import League
from app.domain.aggregates.league.entities import Player, Team
from app.domain.aggregates.league.value_objects import LeagueId, PlayerId, PlayerNickname, TeamId
from app.domain.aggregates.match.aggregate_root import Match
from app.domain.aggregates.match.value_objects import MatchId, SetScore


# ---------------------------------------------------------------------------
# Mock repository factories
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_league_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_id_with_lock = AsyncMock(return_value=None)
    repo.get_by_normalized_title = AsyncMock(return_value=None)
    repo.save = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def mock_match_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_all_by_league = AsyncMock(return_value=[])
    repo.has_matches_for_team = AsyncMock(return_value=False)
    repo.save = AsyncMock(return_value=None)
    repo.delete = AsyncMock(return_value=None)
    return repo


# ---------------------------------------------------------------------------
# Domain object factories
# ---------------------------------------------------------------------------


def make_league(
    title: str = "Test League",
    host_token: str = "test-host-token",
    league_id: LeagueId | None = None,
) -> League:
    league = League.create(title=title, description=None, host_token=host_token)
    if league_id is not None:
        object.__setattr__(league, "league_id", league_id)
    return league


def make_player(nickname: str) -> Player:
    return Player(player_id=PlayerId.generate(), nickname=PlayerNickname(nickname))


def make_team(p1: Player, p2: Player) -> Team:
    pid1, pid2 = p1.player_id, p2.player_id
    if str(pid1.value) > str(pid2.value):
        pid1, pid2 = pid2, pid1
    return Team(team_id=TeamId.generate(), player_id_1=pid1, player_id_2=pid2)


def make_match(
    league_id: LeagueId,
    team1_id: TeamId,
    team2_id: TeamId,
    t1_score: str = "6",
    t2_score: str = "3",
) -> Match:
    return Match.create(league_id, team1_id, team2_id, SetScore(t1_score, t2_score))
