from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import partial

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.create_league_use_case import CreateLeagueUseCase
from app.application.use_cases.delete_match_use_case import DeleteMatchUseCase
from app.application.use_cases.delete_team_use_case import DeleteTeamUseCase
from app.application.use_cases.edit_match_score_use_case import EditMatchScoreUseCase
from app.application.use_cases.edit_player_nickname_use_case import EditPlayerNicknameUseCase
from app.application.use_cases.get_league_roster_use_case import GetLeagueRosterUseCase
from app.application.use_cases.get_match_history_use_case import GetMatchHistoryUseCase
from app.application.use_cases.get_match_history_by_player_use_case import GetMatchHistoryByPlayerUseCase
from app.application.use_cases.get_standings_by_player_use_case import GetStandingsByPlayerUseCase
from app.application.use_cases.get_standings_use_case import GetStandingsUseCase
from app.application.use_cases.submit_match_result_use_case import SubmitMatchResultUseCase
from app.infrastructure.config.database import AsyncSessionFactory
from app.infrastructure.persistence.repositories.league_repository import SqlAlchemyLeagueRepository
from app.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_league_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemyLeagueRepository:
    return SqlAlchemyLeagueRepository(session)


def get_match_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemyMatchRepository:
    return SqlAlchemyMatchRepository(session)


def get_create_league_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> CreateLeagueUseCase:
    return CreateLeagueUseCase(league_repo)


def get_submit_match_result_use_case() -> SubmitMatchResultUseCase:
    uow_factory = partial(SqlAlchemySubmitMatchResultUnitOfWork, AsyncSessionFactory)
    return SubmitMatchResultUseCase(uow_factory)


def get_get_standings_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> GetStandingsUseCase:
    return GetStandingsUseCase(league_repo, match_repo)


def get_get_standings_by_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> GetStandingsByPlayerUseCase:
    return GetStandingsByPlayerUseCase(league_repo, match_repo)


def get_get_match_history_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> GetMatchHistoryUseCase:
    return GetMatchHistoryUseCase(league_repo, match_repo)


def get_get_match_history_by_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> GetMatchHistoryByPlayerUseCase:
    return GetMatchHistoryByPlayerUseCase(league_repo, match_repo)


def get_get_league_roster_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> GetLeagueRosterUseCase:
    return GetLeagueRosterUseCase(league_repo)


def get_edit_player_nickname_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> EditPlayerNicknameUseCase:
    return EditPlayerNicknameUseCase(league_repo)


def get_delete_team_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> DeleteTeamUseCase:
    return DeleteTeamUseCase(league_repo, match_repo)


def get_edit_match_score_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> EditMatchScoreUseCase:
    return EditMatchScoreUseCase(league_repo, match_repo)


def get_delete_match_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> DeleteMatchUseCase:
    return DeleteMatchUseCase(league_repo, match_repo)
