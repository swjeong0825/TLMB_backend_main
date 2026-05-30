from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import partial

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.add_players_use_case import AddPlayersUseCase
from app.application.use_cases.add_alias_to_player_use_case import AddAliasToPlayerUseCase
from app.application.use_cases.create_league_use_case import CreateLeagueUseCase
from app.application.use_cases.delete_match_use_case import DeleteMatchUseCase
from app.application.use_cases.delete_singles_match_use_case import DeleteSinglesMatchUseCase
from app.application.use_cases.delete_pair_use_case import DeletePairUseCase
from app.application.use_cases.edit_match_score_use_case import EditMatchScoreUseCase
from app.application.use_cases.edit_singles_match_score_use_case import EditSinglesMatchScoreUseCase
from app.application.use_cases.edit_player_nickname_use_case import EditPlayerNicknameUseCase
from app.application.use_cases.get_league_admin_info_use_case import GetLeagueAdminInfoUseCase
from app.application.use_cases.get_league_roster_use_case import GetLeagueRosterUseCase
from app.application.use_cases.get_match_history_use_case import GetMatchHistoryUseCase
from app.application.use_cases.get_match_history_by_player_use_case import GetMatchHistoryByPlayerUseCase
from app.application.use_cases.get_standings_by_player_use_case import GetStandingsByPlayerUseCase
from app.application.use_cases.get_standings_use_case import GetStandingsUseCase
from app.application.use_cases.remove_player_from_roster_use_case import RemovePlayerFromRosterUseCase
from app.application.use_cases.remove_alias_from_player_use_case import RemoveAliasFromPlayerUseCase
from app.application.use_cases.search_leagues_by_title_prefix_use_case import (
    SearchLeaguesByTitlePrefixUseCase,
)
from app.application.use_cases.submit_match_result_use_case import SubmitMatchResultUseCase
from app.application.use_cases.submit_singles_match_result_use_case import (
    SubmitSinglesMatchResultUseCase,
)
from app.config import player_match_delete_window_seconds, player_score_edit_window_seconds
from app.infrastructure.config.database import AsyncSessionFactory
from app.infrastructure.persistence.repositories.league_repository import SqlAlchemyLeagueRepository
from app.infrastructure.persistence.repositories.match_repository import SqlAlchemyMatchRepository
from app.infrastructure.persistence.repositories.singles_match_repository import (
    SqlAlchemySinglesMatchRepository,
)
from app.infrastructure.persistence.unit_of_work.submit_match_result_uow import (
    SqlAlchemySubmitMatchResultUnitOfWork,
)
from app.infrastructure.persistence.unit_of_work.submit_singles_match_result_uow import (
    SqlAlchemySubmitSinglesMatchResultUnitOfWork,
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


def get_singles_match_repo(
    session: AsyncSession = Depends(get_db_session),
) -> SqlAlchemySinglesMatchRepository:
    return SqlAlchemySinglesMatchRepository(session)


def get_create_league_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> CreateLeagueUseCase:
    return CreateLeagueUseCase(league_repo)


def get_search_leagues_by_title_prefix_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> SearchLeaguesByTitlePrefixUseCase:
    return SearchLeaguesByTitlePrefixUseCase(league_repo)


def get_submit_match_result_use_case() -> SubmitMatchResultUseCase:
    uow_factory = partial(SqlAlchemySubmitMatchResultUnitOfWork, AsyncSessionFactory)
    return SubmitMatchResultUseCase(uow_factory)


def get_submit_singles_match_result_use_case() -> SubmitSinglesMatchResultUseCase:
    uow_factory = partial(
        SqlAlchemySubmitSinglesMatchResultUnitOfWork, AsyncSessionFactory
    )
    return SubmitSinglesMatchResultUseCase(uow_factory)


def get_get_standings_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> GetStandingsUseCase:
    return GetStandingsUseCase(league_repo, match_repo, singles_match_repo)


def get_get_standings_by_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> GetStandingsByPlayerUseCase:
    return GetStandingsByPlayerUseCase(league_repo, match_repo, singles_match_repo)


def get_get_match_history_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> GetMatchHistoryUseCase:
    return GetMatchHistoryUseCase(league_repo, match_repo, singles_match_repo)


def get_get_match_history_by_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> GetMatchHistoryByPlayerUseCase:
    return GetMatchHistoryByPlayerUseCase(league_repo, match_repo, singles_match_repo)


def get_get_league_roster_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> GetLeagueRosterUseCase:
    return GetLeagueRosterUseCase(league_repo)


def get_get_league_admin_info_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> GetLeagueAdminInfoUseCase:
    return GetLeagueAdminInfoUseCase(league_repo)


def get_edit_player_nickname_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> EditPlayerNicknameUseCase:
    return EditPlayerNicknameUseCase(league_repo)


def get_delete_pair_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> DeletePairUseCase:
    return DeletePairUseCase(league_repo, match_repo)


def get_edit_match_score_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> EditMatchScoreUseCase:
    return EditMatchScoreUseCase(
        league_repo,
        match_repo,
        window_seconds=player_score_edit_window_seconds(),
    )


def get_delete_match_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    match_repo: SqlAlchemyMatchRepository = Depends(get_match_repo),
) -> DeleteMatchUseCase:
    return DeleteMatchUseCase(
        league_repo,
        match_repo,
        window_seconds=player_match_delete_window_seconds(),
    )


def get_edit_singles_match_score_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> EditSinglesMatchScoreUseCase:
    return EditSinglesMatchScoreUseCase(
        league_repo,
        singles_match_repo,
        window_seconds=player_score_edit_window_seconds(),
    )


def get_delete_singles_match_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
    singles_match_repo: SqlAlchemySinglesMatchRepository = Depends(get_singles_match_repo),
) -> DeleteSinglesMatchUseCase:
    return DeleteSinglesMatchUseCase(
        league_repo,
        singles_match_repo,
        window_seconds=player_match_delete_window_seconds(),
    )


def get_add_players_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> AddPlayersUseCase:
    return AddPlayersUseCase(league_repo)


def get_add_alias_to_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> AddAliasToPlayerUseCase:
    return AddAliasToPlayerUseCase(league_repo)


def get_remove_player_from_roster_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> RemovePlayerFromRosterUseCase:
    return RemovePlayerFromRosterUseCase(league_repo)


def get_remove_alias_from_player_use_case(
    league_repo: SqlAlchemyLeagueRepository = Depends(get_league_repo),
) -> RemoveAliasFromPlayerUseCase:
    return RemoveAliasFromPlayerUseCase(league_repo)
