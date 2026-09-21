from app.application.unit_of_work.base import BaseUnitOfWork
from app.domain.aggregates.league.repository import LeagueRepository
from app.domain.aggregates.planned_match.repository import PlannedMatchRepository


class DeletePlannedMatchUnitOfWork(BaseUnitOfWork):
    league_repo: LeagueRepository
    planned_match_repo: PlannedMatchRepository
