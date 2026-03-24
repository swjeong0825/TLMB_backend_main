from __future__ import annotations

from abc import abstractmethod

from app.application.unit_of_work.base import BaseUnitOfWork
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.match.repository import MatchRepository


class SubmitMatchResultUnitOfWork(BaseUnitOfWork):
    league_repo: LeagueRepository
    match_repo: MatchRepository

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
