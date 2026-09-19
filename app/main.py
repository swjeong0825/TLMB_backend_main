from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers.admin_router import router as admin_router
from app.api.routers.league_router import router as league_router
from app.api.routers.planned_match_router import router as planned_match_router
from app.rate_limit import register_rate_limit_middleware
from app.domain.exceptions import (
    CannotRemoveCanonicalNicknameError,
    DuplicatePairMatchupMatchError,
    DuplicateSinglesMatchupMatchError,
    InvalidLeagueRulesError,
    InvalidPlayerRatingError,
    InvalidPlayerNicknameError,
    InvalidPlannedMatchError,
    InvalidSetScoreError,
    LastNicknameError,
    LeagueNotFoundError,
    LeagueTitleAlreadyExistsError,
    MatchDeleteWindowExpiredError,
    MatchEditWindowExpiredError,
    MatchNotFoundError,
    NicknameAlreadyInUseError,
    PlayerHasParticipationError,
    PlayerNotFoundError,
    RosterMembershipRequiredError,
    SamePlayerOnBothSidesError,
    SamePlayerOnBothPairsError,
    SamePlayerWithinSinglePairError,
    SamePairOnBothSidesError,
    PairConflictError,
    PairHasMatchesError,
    PairNotFoundError,
    UnauthorizedError,
)

app = FastAPI(title="Tennis League Manager", version="1.0.0")

ALLOWED_ORIGINS = [
    "https://tlmb.swjapps.com",
    "https://www.tlmb.swjapps.com",
    "https://tlmb-test-site.swjeong0825.workers.dev"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_rate_limit_middleware(app)

app.include_router(league_router)
app.include_router(admin_router)
app.include_router(planned_match_router)


@app.exception_handler(InvalidPlayerNicknameError)
@app.exception_handler(InvalidPlannedMatchError)
async def invalid_nickname_or_plan_handler(
    request: Request, exc: InvalidPlayerNicknameError | InvalidPlannedMatchError
) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"error": type(exc).__name__, "detail": str(exc)}
    )


@app.exception_handler(LeagueNotFoundError)
async def league_not_found_handler(request: Request, exc: LeagueNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "LeagueNotFoundError", "detail": str(exc)})


@app.exception_handler(PlayerNotFoundError)
async def player_not_found_handler(request: Request, exc: PlayerNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "PlayerNotFoundError", "detail": str(exc)})


@app.exception_handler(PairNotFoundError)
async def pair_not_found_handler(request: Request, exc: PairNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "PairNotFoundError", "detail": str(exc)})


@app.exception_handler(MatchNotFoundError)
async def match_not_found_handler(request: Request, exc: MatchNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "MatchNotFoundError", "detail": str(exc)})


@app.exception_handler(UnauthorizedError)
async def unauthorized_handler(request: Request, exc: UnauthorizedError) -> JSONResponse:
    return JSONResponse(status_code=401, content={"error": "UnauthorizedError", "detail": str(exc)})


@app.exception_handler(LeagueTitleAlreadyExistsError)
async def league_title_exists_handler(request: Request, exc: LeagueTitleAlreadyExistsError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "LeagueTitleAlreadyExistsError", "detail": str(exc)})


@app.exception_handler(PairConflictError)
async def pair_conflict_handler(request: Request, exc: PairConflictError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "PairConflictError", "detail": str(exc)})


@app.exception_handler(NicknameAlreadyInUseError)
async def nickname_in_use_handler(request: Request, exc: NicknameAlreadyInUseError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "NicknameAlreadyInUseError", "detail": str(exc)})


@app.exception_handler(CannotRemoveCanonicalNicknameError)
async def cannot_remove_canonical_nickname_handler(
    request: Request, exc: CannotRemoveCanonicalNicknameError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "CannotRemoveCanonicalNicknameError",
            "detail": str(exc),
            "player_id": exc.player_id,
            "canonical_nickname": exc.canonical_nickname,
        },
    )


@app.exception_handler(LastNicknameError)
async def last_nickname_handler(
    request: Request, exc: LastNicknameError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "LastNicknameError",
            "detail": str(exc),
            "player_id": exc.player_id,
        },
    )


@app.exception_handler(PairHasMatchesError)
async def pair_has_matches_handler(request: Request, exc: PairHasMatchesError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "PairHasMatchesError", "detail": str(exc)})


@app.exception_handler(SamePairOnBothSidesError)
async def same_pair_handler(request: Request, exc: SamePairOnBothSidesError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"error": "SamePairOnBothSidesError", "detail": str(exc)})


@app.exception_handler(DuplicatePairMatchupMatchError)
async def duplicate_pair_matchup_match_handler(
    request: Request, exc: DuplicatePairMatchupMatchError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "DuplicatePairMatchupMatchError", "detail": str(exc)},
    )


@app.exception_handler(DuplicateSinglesMatchupMatchError)
async def duplicate_singles_matchup_match_handler(
    request: Request, exc: DuplicateSinglesMatchupMatchError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": "DuplicateSinglesMatchupMatchError", "detail": str(exc)},
    )


@app.exception_handler(SamePlayerWithinSinglePairError)
async def same_player_single_pair_handler(request: Request, exc: SamePlayerWithinSinglePairError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "SamePlayerWithinSinglePairError", "detail": str(exc)})


@app.exception_handler(SamePlayerOnBothPairsError)
async def same_player_both_pairs_handler(request: Request, exc: SamePlayerOnBothPairsError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "SamePlayerOnBothPairsError", "detail": str(exc)})


@app.exception_handler(SamePlayerOnBothSidesError)
async def same_player_singles_handler(
    request: Request, exc: SamePlayerOnBothSidesError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "SamePlayerOnBothSidesError", "detail": str(exc)},
    )


@app.exception_handler(InvalidSetScoreError)
async def invalid_score_handler(request: Request, exc: InvalidSetScoreError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "InvalidSetScoreError", "detail": str(exc)})


@app.exception_handler(InvalidLeagueRulesError)
async def invalid_league_rules_handler(request: Request, exc: InvalidLeagueRulesError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "InvalidLeagueRulesError", "detail": str(exc)})


@app.exception_handler(InvalidPlayerRatingError)
async def invalid_player_rating_handler(
    request: Request, exc: InvalidPlayerRatingError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": "InvalidPlayerRatingError", "detail": str(exc)},
    )


@app.exception_handler(RosterMembershipRequiredError)
async def roster_membership_required_handler(
    request: Request, exc: RosterMembershipRequiredError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "RosterMembershipRequiredError",
            "detail": str(exc),
            "missing_nicknames": list(exc.missing_nicknames),
        },
    )


@app.exception_handler(PlayerHasParticipationError)
async def player_has_participation_handler(
    request: Request, exc: PlayerHasParticipationError
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "error": "PlayerHasParticipationError",
            "detail": str(exc),
            "player_id": exc.player_id,
            "pairs_count": exc.pairs_count,
            "matches_count": exc.matches_count,
        },
    )


@app.exception_handler(MatchEditWindowExpiredError)
async def match_edit_window_expired_handler(
    request: Request, exc: MatchEditWindowExpiredError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "MatchEditWindowExpiredError",
            "detail": str(exc),
            "match_id": exc.match_id,
            "window_seconds": exc.window_seconds,
            "age_seconds": exc.age_seconds,
        },
    )


@app.exception_handler(MatchDeleteWindowExpiredError)
async def match_delete_window_expired_handler(
    request: Request, exc: MatchDeleteWindowExpiredError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "MatchDeleteWindowExpiredError",
            "detail": str(exc),
            "match_id": exc.match_id,
            "window_seconds": exc.window_seconds,
            "age_seconds": exc.age_seconds,
        },
    )
