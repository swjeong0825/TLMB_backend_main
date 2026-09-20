from __future__ import annotations

from abc import abstractmethod

from app.application.unit_of_work.base import BaseUnitOfWork
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.planned_match.repository import PlannedMatchRepository
from app.domain.aggregates.singles_match.repository import SinglesMatchRepository


class SubmitSinglesMatchResultUnitOfWork(BaseUnitOfWork):
    league_repo: LeagueRepository
    planned_match_repo: PlannedMatchRepository
    singles_match_repo: SinglesMatchRepository

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
