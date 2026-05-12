from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from starlette.requests import Request

from app.api.schemas.admin_schemas import (
    AddEligiblePlayersRequest,
    AddEligiblePlayersResponse,
    EditMatchScoreRequest,
    EditMatchScoreResponse,
    EditPlayerNicknameRequest,
    EditPlayerNicknameResponse,
)
from app.api.schemas.league_schemas import EligiblePlayerEntrySchema
from app.application.use_cases.add_eligible_players_use_case import (
    AddEligiblePlayersCommand,
    AddEligiblePlayersUseCase,
)
from app.application.use_cases.delete_match_use_case import DeleteMatchCommand, DeleteMatchUseCase
from app.application.use_cases.delete_team_use_case import DeleteTeamCommand, DeleteTeamUseCase
from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.application.use_cases.edit_player_nickname_use_case import (
    EditPlayerNicknameCommand,
    EditPlayerNicknameUseCase,
)
from app.application.use_cases.remove_eligible_player_use_case import (
    RemoveEligiblePlayerCommand,
    RemoveEligiblePlayerUseCase,
)
from app.dependencies import (
    get_add_eligible_players_use_case,
    get_delete_match_use_case,
    get_delete_team_use_case,
    get_edit_match_score_use_case,
    get_edit_player_nickname_use_case,
    get_remove_eligible_player_use_case,
)
from app.rate_limit import limiter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.patch(
    "/leagues/{league_id}/players/{player_id}",
    status_code=status.HTTP_200_OK,
    response_model=EditPlayerNicknameResponse,
)
@limiter.limit("60/minute")
async def edit_player_nickname(
    request: Request,
    league_id: str,
    player_id: str,
    body: EditPlayerNicknameRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: EditPlayerNicknameUseCase = Depends(get_edit_player_nickname_use_case),
) -> EditPlayerNicknameResponse:
    result = await use_case.execute(
        EditPlayerNicknameCommand(
            host_token=x_host_token,
            league_id=league_id,
            player_id=player_id,
            new_nickname=body.new_nickname,
        )
    )
    return EditPlayerNicknameResponse(
        player_id=result.player_id, new_nickname=result.new_nickname
    )


@router.delete(
    "/leagues/{league_id}/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def delete_team(
    request: Request,
    league_id: str,
    team_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: DeleteTeamUseCase = Depends(get_delete_team_use_case),
) -> None:
    await use_case.execute(
        DeleteTeamCommand(
            host_token=x_host_token,
            league_id=league_id,
            team_id=team_id,
        )
    )


@router.patch(
    "/leagues/{league_id}/matches/{match_id}",
    status_code=status.HTTP_200_OK,
    response_model=EditMatchScoreResponse,
)
@limiter.limit("60/minute")
async def edit_match_score(
    request: Request,
    league_id: str,
    match_id: str,
    body: EditMatchScoreRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: EditMatchScoreUseCase = Depends(get_edit_match_score_use_case),
) -> EditMatchScoreResponse:
    result = await use_case.execute(
        EditMatchScoreCommand(
            host_token=x_host_token,
            league_id=league_id,
            match_id=match_id,
            team1_score=body.team1_score,
            team2_score=body.team2_score,
        )
    )
    return EditMatchScoreResponse(
        match_id=result.match_id,
        team1_score=result.team1_score,
        team2_score=result.team2_score,
    )


@router.delete(
    "/leagues/{league_id}/matches/{match_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def delete_match(
    request: Request,
    league_id: str,
    match_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: DeleteMatchUseCase = Depends(get_delete_match_use_case),
) -> None:
    await use_case.execute(
        DeleteMatchCommand(
            host_token=x_host_token,
            league_id=league_id,
            match_id=match_id,
        )
    )


@router.post(
    "/leagues/{league_id}/eligible-players",
    status_code=status.HTTP_201_CREATED,
    response_model=AddEligiblePlayersResponse,
)
@limiter.limit("60/minute")
async def add_eligible_players(
    request: Request,
    league_id: str,
    body: AddEligiblePlayersRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: AddEligiblePlayersUseCase = Depends(get_add_eligible_players_use_case),
) -> AddEligiblePlayersResponse:
    result = await use_case.execute(
        AddEligiblePlayersCommand(
            host_token=x_host_token,
            league_id=league_id,
            nicknames=body.nicknames,
        )
    )
    return AddEligiblePlayersResponse(
        eligible_players=[
            EligiblePlayerEntrySchema(
                eligible_player_id=e.eligible_player_id,
                nickname=e.nickname,
            )
            for e in result.eligible_players
        ],
    )


@router.delete(
    "/leagues/{league_id}/eligible-players/{eligible_player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def remove_eligible_player(
    request: Request,
    league_id: str,
    eligible_player_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: RemoveEligiblePlayerUseCase = Depends(get_remove_eligible_player_use_case),
) -> None:
    await use_case.execute(
        RemoveEligiblePlayerCommand(
            host_token=x_host_token,
            league_id=league_id,
            eligible_player_id=eligible_player_id,
        )
    )
