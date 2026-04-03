from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.admin_router import router as admin_router
from app.api.routers.league_router import router as league_router
from app.domain.exceptions import (
    InvalidSetScoreError,
    LeagueNotFoundError,
    LeagueTitleAlreadyExistsError,
    MatchNotFoundError,
    NicknameAlreadyInUseError,
    PlayerNotFoundError,
    SamePlayerOnBothTeamsError,
    SamePlayerWithinSingleTeamError,
    SameTeamOnBothSidesError,
    TeamConflictError,
    TeamHasMatchesError,
    TeamNotFoundError,
    UnauthorizedError,
)

app = FastAPI(title="Tennis League Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(league_router)
app.include_router(admin_router)


@app.exception_handler(LeagueNotFoundError)
async def league_not_found_handler(request: Request, exc: LeagueNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "LeagueNotFoundError", "detail": str(exc)})


@app.exception_handler(PlayerNotFoundError)
async def player_not_found_handler(request: Request, exc: PlayerNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "PlayerNotFoundError", "detail": str(exc)})


@app.exception_handler(TeamNotFoundError)
async def team_not_found_handler(request: Request, exc: TeamNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "TeamNotFoundError", "detail": str(exc)})


@app.exception_handler(MatchNotFoundError)
async def match_not_found_handler(request: Request, exc: MatchNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "MatchNotFoundError", "detail": str(exc)})


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": "UnauthorizedError", "detail": str(exc)})


@app.exception_handler(LeagueTitleAlreadyExistsError)
async def league_title_exists_handler(request: Request, exc: LeagueTitleAlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "LeagueTitleAlreadyExistsError", "detail": str(exc)})


@app.exception_handler(TeamConflictError)
async def team_conflict_handler(request: Request, exc: TeamConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "TeamConflictError", "detail": str(exc)})


@app.exception_handler(NicknameAlreadyInUseError)
async def nickname_in_use_handler(request: Request, exc: NicknameAlreadyInUseError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "NicknameAlreadyInUseError", "detail": str(exc)})


@app.exception_handler(TeamHasMatchesError)
async def team_has_matches_handler(request: Request, exc: TeamHasMatchesError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "TeamHasMatchesError", "detail": str(exc)})


@app.exception_handler(SameTeamOnBothSidesError)
async def same_team_handler(request: Request, exc: SameTeamOnBothSidesError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "SameTeamOnBothSidesError", "detail": str(exc)})


@app.exception_handler(SamePlayerWithinSingleTeamError)
async def same_player_single_team_handler(request: Request, exc: SamePlayerWithinSingleTeamError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "SamePlayerWithinSingleTeamError", "detail": str(exc)})


@app.exception_handler(SamePlayerOnBothTeamsError)
async def same_player_both_teams_handler(request: Request, exc: SamePlayerOnBothTeamsError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "SamePlayerOnBothTeamsError", "detail": str(exc)})


@app.exception_handler(InvalidSetScoreError)
async def invalid_score_handler(request: Request, exc: InvalidSetScoreError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "InvalidSetScoreError", "detail": str(exc)})
