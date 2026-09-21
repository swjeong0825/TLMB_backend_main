from uuid import UUID

from fastapi import APIRouter, Depends, Request

from app.api.schemas.planned_match_schemas import PlannedMatchesResponse, PlannedMatchSchema, UploadPlannedMatchesRequest
from app.application.use_cases.get_planned_matches_use_case import GetPlannedMatchesQuery, GetPlannedMatchesUseCase
from app.application.use_cases.delete_planned_match_use_case import DeletePlannedMatchCommand, DeletePlannedMatchUseCase
from app.application.use_cases.planned_match_dtos import PlannedMatchRecord
from app.application.use_cases.upload_planned_matches_use_case import UploadPlannedMatchesCommand, UploadPlannedMatchesUseCase
from app.dependencies import get_delete_planned_match_use_case, get_get_planned_matches_use_case, get_upload_planned_matches_use_case
from app.rate_limit import limiter


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


@router.delete("/{planned_match_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_planned_match(
    request: Request,
    league_id: UUID,
    planned_match_id: UUID,
    use_case: DeletePlannedMatchUseCase = Depends(get_delete_planned_match_use_case),
) -> None:
    await use_case.execute(DeletePlannedMatchCommand(
        league_id=str(league_id), planned_match_id=planned_match_id,
    ))


@router.get("", status_code=200, response_model=PlannedMatchesResponse)
async def get_planned_matches(
    league_id: UUID,
    use_case: GetPlannedMatchesUseCase = Depends(get_get_planned_matches_use_case),
) -> PlannedMatchesResponse:
    matches = await use_case.execute(GetPlannedMatchesQuery(league_id=str(league_id)))
    return PlannedMatchesResponse(matches=[PlannedMatchSchema(id=match.id, value=match.value) for match in matches])
