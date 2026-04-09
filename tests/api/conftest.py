"""Shared fixtures for API-layer unit tests.

All use cases are replaced with AsyncMock objects via FastAPI dependency
overrides.  No database is touched.
"""
from __future__ import annotations

import os

# Set DATABASE_URL before any app module is imported so the database module
# can initialize without a real connection.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://sunwoojeong@localhost:5432/tennis_league_test")

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.dependencies import (
    get_create_league_use_case,
    get_delete_match_use_case,
    get_delete_team_use_case,
    get_edit_match_score_use_case,
    get_edit_player_nickname_use_case,
    get_get_league_roster_use_case,
    get_get_match_history_use_case,
    get_get_match_history_by_player_use_case,
    get_get_standings_by_player_use_case,
    get_get_standings_use_case,
    get_search_leagues_by_title_prefix_use_case,
    get_submit_match_result_use_case,
)
from app.main import app


@pytest.fixture
def mock_create_league_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_search_leagues_uc() -> AsyncMock:
    m = AsyncMock()
    m.execute = AsyncMock(return_value=[])
    return m


@pytest.fixture
def mock_submit_match_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_get_standings_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_get_match_history_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_get_roster_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_edit_player_nickname_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_delete_team_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_edit_match_score_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_delete_match_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_get_match_history_by_player_uc() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_get_standings_by_player_uc() -> AsyncMock:
    return AsyncMock()


@pytest_asyncio.fixture
async def client(
    mock_create_league_uc: AsyncMock,
    mock_search_leagues_uc: AsyncMock,
    mock_submit_match_uc: AsyncMock,
    mock_get_standings_uc: AsyncMock,
    mock_get_match_history_uc: AsyncMock,
    mock_get_roster_uc: AsyncMock,
    mock_edit_player_nickname_uc: AsyncMock,
    mock_delete_team_uc: AsyncMock,
    mock_edit_match_score_uc: AsyncMock,
    mock_delete_match_uc: AsyncMock,
    mock_get_match_history_by_player_uc: AsyncMock,
    mock_get_standings_by_player_uc: AsyncMock,
) -> AsyncClient:
    app.dependency_overrides[get_create_league_use_case] = lambda: mock_create_league_uc
    app.dependency_overrides[get_search_leagues_by_title_prefix_use_case] = (
        lambda: mock_search_leagues_uc
    )
    app.dependency_overrides[get_submit_match_result_use_case] = lambda: mock_submit_match_uc
    app.dependency_overrides[get_get_standings_use_case] = lambda: mock_get_standings_uc
    app.dependency_overrides[get_get_match_history_use_case] = lambda: mock_get_match_history_uc
    app.dependency_overrides[get_get_league_roster_use_case] = lambda: mock_get_roster_uc
    app.dependency_overrides[get_edit_player_nickname_use_case] = (
        lambda: mock_edit_player_nickname_uc
    )
    app.dependency_overrides[get_delete_team_use_case] = lambda: mock_delete_team_uc
    app.dependency_overrides[get_edit_match_score_use_case] = lambda: mock_edit_match_score_uc
    app.dependency_overrides[get_delete_match_use_case] = lambda: mock_delete_match_uc
    app.dependency_overrides[get_get_match_history_by_player_use_case] = (
        lambda: mock_get_match_history_by_player_uc
    )
    app.dependency_overrides[get_get_standings_by_player_use_case] = (
        lambda: mock_get_standings_by_player_uc
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
