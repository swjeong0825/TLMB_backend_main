from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status
from starlette.requests import Request

from app.api.schemas.admin_schemas import (
    AddPlayerAliasRequest,
    AddPlayersRequest,
    AddPlayersResponse,
    EditMatchScoreRequest,
    EditMatchScoreResponse,
    EditSinglesMatchScoreRequest,
    EditSinglesMatchScoreResponse,
    EditPlayerNicknameRequest,
    EditPlayerNicknameResponse,
    GetLeagueAdminInfoResponse,
    PlayerAliasResponse,
)
from app.application.use_cases.add_alias_to_player_use_case import (
    AddAliasToPlayerCommand,
    AddAliasToPlayerUseCase,
)
from app.api.schemas.league_schemas import PlayerEntrySchema
from app.application.use_cases.add_players_use_case import (
    AddPlayersCommand,
    AddPlayersUseCase,
)
from app.application.use_cases.delete_match_use_case import DeleteMatchCommand, DeleteMatchUseCase
from app.application.use_cases.delete_singles_match_use_case import (
    DeleteSinglesMatchCommand,
    DeleteSinglesMatchUseCase,
)
from app.application.use_cases.delete_pair_use_case import DeletePairCommand, DeletePairUseCase
from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.application.use_cases.edit_singles_match_score_use_case import (
    EditSinglesMatchScoreCommand,
    EditSinglesMatchScoreUseCase,
)
from app.application.use_cases.edit_player_nickname_use_case import (
    EditPlayerNicknameCommand,
    EditPlayerNicknameUseCase,
)
from app.application.use_cases.get_league_admin_info_use_case import (
    GetLeagueAdminInfoQuery,
    GetLeagueAdminInfoUseCase,
)
from app.application.use_cases.remove_player_from_roster_use_case import (
    RemovePlayerFromRosterCommand,
    RemovePlayerFromRosterUseCase,
)
from app.application.use_cases.remove_alias_from_player_use_case import (
    RemoveAliasFromPlayerCommand,
    RemoveAliasFromPlayerUseCase,
)
from app.dependencies import (
    get_add_alias_to_player_use_case,
    get_add_players_use_case,
    get_delete_match_use_case,
    get_delete_singles_match_use_case,
    get_delete_pair_use_case,
    get_edit_match_score_use_case,
    get_edit_singles_match_score_use_case,
    get_edit_player_nickname_use_case,
    get_get_league_admin_info_use_case,
    get_remove_alias_from_player_use_case,
    get_remove_player_from_roster_use_case,
)
from app.rate_limit import limiter

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/leagues/{league_id}",
    status_code=status.HTTP_200_OK,
    response_model=GetLeagueAdminInfoResponse,
)
@limiter.limit("60/minute")
async def get_league_admin_info(
    request: Request,
    league_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: GetLeagueAdminInfoUseCase = Depends(get_get_league_admin_info_use_case),
) -> GetLeagueAdminInfoResponse:
    result = await use_case.execute(
        GetLeagueAdminInfoQuery(
            host_token=x_host_token,
            league_id=league_id,
        )
    )
    return GetLeagueAdminInfoResponse(host_email=result.host_email)


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
            rating=body.rating,
            rating_supplied="rating" in body.model_fields_set,
        )
    )
    return EditPlayerNicknameResponse(
        player_id=result.player_id,
        new_nickname=result.new_nickname,
        rating=result.rating,
    )


@router.delete(
    "/leagues/{league_id}/pairs/{pair_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def delete_pair(
    request: Request,
    league_id: str,
    pair_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: DeletePairUseCase = Depends(get_delete_pair_use_case),
) -> None:
    await use_case.execute(
        DeletePairCommand(
            host_token=x_host_token,
            league_id=league_id,
            pair_id=pair_id,
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
            pair1_score=body.pair1_score,
            pair2_score=body.pair2_score,
        )
    )
    return EditMatchScoreResponse(
        match_id=result.match_id,
        pair1_score=result.pair1_score,
        pair2_score=result.pair2_score,
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


@router.patch(
    "/leagues/{league_id}/singles-matches/{match_id}",
    status_code=status.HTTP_200_OK,
    response_model=EditSinglesMatchScoreResponse,
)
@limiter.limit("60/minute")
async def edit_singles_match_score(
    request: Request,
    league_id: str,
    match_id: str,
    body: EditSinglesMatchScoreRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: EditSinglesMatchScoreUseCase = Depends(
        get_edit_singles_match_score_use_case
    ),
) -> EditSinglesMatchScoreResponse:
    result = await use_case.execute(
        EditSinglesMatchScoreCommand(
            host_token=x_host_token,
            league_id=league_id,
            match_id=match_id,
            player1_score=body.player1_score,
            player2_score=body.player2_score,
        )
    )
    return EditSinglesMatchScoreResponse(
        match_id=result.match_id,
        player1_score=result.player1_score,
        player2_score=result.player2_score,
    )


@router.delete(
    "/leagues/{league_id}/singles-matches/{match_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def delete_singles_match(
    request: Request,
    league_id: str,
    match_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: DeleteSinglesMatchUseCase = Depends(get_delete_singles_match_use_case),
) -> None:
    await use_case.execute(
        DeleteSinglesMatchCommand(
            host_token=x_host_token,
            league_id=league_id,
            match_id=match_id,
        )
    )


@router.post(
    "/leagues/{league_id}/players",
    status_code=status.HTTP_201_CREATED,
    response_model=AddPlayersResponse,
)
@limiter.limit("60/minute")
async def add_players(
    request: Request,
    league_id: str,
    body: AddPlayersRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: AddPlayersUseCase = Depends(get_add_players_use_case),
) -> AddPlayersResponse:
    result = await use_case.execute(
        AddPlayersCommand(
            host_token=x_host_token,
            league_id=league_id,
            nicknames=(
                [player.nickname for player in body.players]
                if body.players is not None
                else list(body.nicknames or [])
            ),
            ratings=(
                [player.rating for player in body.players]
                if body.players is not None
                else None
            ),
        )
    )
    return AddPlayersResponse(
        players=[
            PlayerEntrySchema(
                player_id=p.player_id,
                nickname=p.nickname,
                rating=p.rating,
            )
            for p in result.players
        ],
    )


@router.post(
    "/leagues/{league_id}/players/{player_id}/aliases",
    status_code=status.HTTP_201_CREATED,
    response_model=PlayerAliasResponse,
)
@limiter.limit("60/minute")
async def add_player_alias(
    request: Request,
    league_id: str,
    player_id: str,
    body: AddPlayerAliasRequest,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: AddAliasToPlayerUseCase = Depends(get_add_alias_to_player_use_case),
) -> PlayerAliasResponse:
    result = await use_case.execute(
        AddAliasToPlayerCommand(
            host_token=x_host_token,
            league_id=league_id,
            player_id=player_id,
            alias=body.alias,
        )
    )
    return PlayerAliasResponse(
        player_id=result.player_id,
        nickname=result.nickname,
        aliases=result.aliases,
    )


@router.delete(
    "/leagues/{league_id}/players/{player_id}/aliases/{alias}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def remove_player_alias(
    request: Request,
    league_id: str,
    player_id: str,
    alias: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: RemoveAliasFromPlayerUseCase = Depends(
        get_remove_alias_from_player_use_case
    ),
) -> None:
    await use_case.execute(
        RemoveAliasFromPlayerCommand(
            host_token=x_host_token,
            league_id=league_id,
            player_id=player_id,
            alias=alias,
        )
    )


@router.delete(
    "/leagues/{league_id}/players/{player_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("60/minute")
async def remove_player_from_roster(
    request: Request,
    league_id: str,
    player_id: str,
    x_host_token: str = Header(..., alias="X-Host-Token"),
    use_case: RemovePlayerFromRosterUseCase = Depends(get_remove_player_from_roster_use_case),
) -> None:
    await use_case.execute(
        RemovePlayerFromRosterCommand(
            host_token=x_host_token,
            league_id=league_id,
            player_id=player_id,
        )
    )
