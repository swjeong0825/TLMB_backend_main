"""Unit tests for SearchLeaguesByTitlePrefixUseCase."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.application.use_cases.search_leagues_by_title_prefix_use_case import (
    LeagueListItem,
    SearchLeaguesByTitlePrefixQuery,
    SearchLeaguesByTitlePrefixUseCase,
)


@pytest.mark.asyncio
async def test_execute_returns_league_list_items() -> None:
    repo = AsyncMock()
    repo.search_by_title_prefix = AsyncMock(
        return_value=[("u1", "A League"), ("u2", "Another")]
    )
    uc = SearchLeaguesByTitlePrefixUseCase(repo)
    out = await uc.execute(SearchLeaguesByTitlePrefixQuery("a", 10))
    assert out == [
        LeagueListItem(league_id="u1", title="A League"),
        LeagueListItem(league_id="u2", title="Another"),
    ]
    repo.search_by_title_prefix.assert_awaited_once_with("a", 10)


@pytest.mark.asyncio
async def test_execute_clamps_limit_to_max() -> None:
    repo = AsyncMock()
    repo.search_by_title_prefix = AsyncMock(return_value=[])
    uc = SearchLeaguesByTitlePrefixUseCase(repo)
    await uc.execute(SearchLeaguesByTitlePrefixQuery("x", 500))
    repo.search_by_title_prefix.assert_awaited_once_with("x", SearchLeaguesByTitlePrefixUseCase.MAX_LIMIT)


@pytest.mark.asyncio
async def test_execute_clamps_non_positive_limit_to_one() -> None:
    repo = AsyncMock()
    repo.search_by_title_prefix = AsyncMock(return_value=[])
    uc = SearchLeaguesByTitlePrefixUseCase(repo)
    await uc.execute(SearchLeaguesByTitlePrefixQuery("x", 0))
    repo.search_by_title_prefix.assert_awaited_once_with("x", 1)
