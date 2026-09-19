from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.schemas.planned_match_schemas import PlannedMatchesResponse, PlannedMatchSchema, UploadPlannedMatchesRequest
from app.application.use_cases.get_planned_matches_use_case import GetPlannedMatchesQuery, GetPlannedMatchesUseCase
from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.application.use_cases.upload_planned_matches_use_case import UploadPlannedMatchesCommand, UploadPlannedMatchesUseCase
from app.dependencies import get_get_planned_matches_use_case, get_upload_planned_matches_use_case


router = APIRouter(prefix="/leagues/{league_id}/planned-matches", tags=["leagues"])


@router.post("", status_code=200, response_model=PlannedMatchesResponse)
async def upload_planned_matches(
    league_id: UUID,
    body: UploadPlannedMatchesRequest,
    use_case: UploadPlannedMatchesUseCase = Depends(get_upload_planned_matches_use_case),
) -> PlannedMatchesResponse:
    matches = await use_case.execute(UploadPlannedMatchesCommand(
        league_id=str(league_id),
        matches=[PlannedMatchRecord(match.id, match.value) for match in body.matches],
    ))
    return PlannedMatchesResponse(matches=[PlannedMatchSchema(id=match.id, value=match.value) for match in matches])


@router.get("", status_code=200, response_model=PlannedMatchesResponse)
async def get_planned_matches(
    league_id: UUID,
    use_case: GetPlannedMatchesUseCase = Depends(get_get_planned_matches_use_case),
) -> PlannedMatchesResponse:
    matches = await use_case.execute(GetPlannedMatchesQuery(league_id=str(league_id)))
    return PlannedMatchesResponse(matches=[PlannedMatchSchema(id=match.id, value=match.value) for match in matches])
