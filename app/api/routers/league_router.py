from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from starlette.requests import Request

# league router is getting admin functionalites for recently created matches
from app.api.schemas.admin_schemas import (
    EditMatchScoreRequest,
    EditMatchScoreResponse,
)
from app.api.schemas.league_schemas import (
    CreateLeagueRequest,
    CreateLeagueResponse,
    GetLeagueRosterResponse,
    GetMatchHistoryResponse,
    GetStandingsResponse,
    LeagueRulesResponseSchema,
    MatchHistoryRecordSchema,
    PlayerEntrySchema,
    StandingsEntrySchema,
    LeagueListItemSchema,
    SearchLeaguesResponse,
    SubmitMatchResultRequest,
    SubmitMatchResultResponse,
    TeamEntrySchema,
)
from app.config import player_match_delete_window_seconds, player_score_edit_window_seconds
from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
)
from app.application.use_cases.delete_match_use_case import (
    DeleteMatchCommand,
    DeleteMatchUseCase,
)
from app.application.use_cases.edit_match_score_use_case import (
    EditMatchScoreCommand,
    EditMatchScoreUseCase,
)
from app.application.use_cases.get_league_roster_use_case import GetLeagueRosterQuery, GetLeagueRosterUseCase
from app.application.use_cases.get_match_history_use_case import GetMatchHistoryQuery, GetMatchHistoryUseCase
from app.application.use_cases.get_standings_by_player_use_case import (
    GetStandingsByPlayerQuery,
    GetStandingsByPlayerUseCase,
)
from app.application.use_cases.get_standings_use_case import GetStandingsQuery, GetStandingsUseCase
from app.application.use_cases.get_match_history_by_player_use_case import (
    GetMatchHistoryByPlayerQuery,
    GetMatchHistoryByPlayerUseCase,
)
from app.application.use_cases.search_leagues_by_title_prefix_use_case import (
    SearchLeaguesByTitlePrefixQuery,
    SearchLeaguesByTitlePrefixUseCase,
)
from app.application.use_cases.submit_match_result_use_case import (
    SubmitMatchResultCommand,
    SubmitMatchResultUseCase,
)
from app.dependencies import (
    get_create_league_use_case,
    get_delete_match_use_case,
    get_edit_match_score_use_case,
    get_get_league_roster_use_case,
    get_get_match_history_by_player_use_case,
    get_get_match_history_use_case,
    get_get_standings_by_player_use_case,
    get_get_standings_use_case,
    get_search_leagues_by_title_prefix_use_case,
    get_submit_match_result_use_case,
)
from app.rate_limit import limiter

router = APIRouter(tags=["leagues"])


@router.post("/leagues", status_code=status.HTTP_201_CREATED, response_model=CreateLeagueResponse)
@limiter.limit("15/minute")
async def create_league(
    request: Request,
    body: CreateLeagueRequest,
    use_case: CreateLeagueUseCase = Depends(get_create_league_use_case),
) -> CreateLeagueResponse:
    result = await use_case.execute(
        CreateLeagueCommand(
            title=body.title,
            host_email=body.host_email,
            description=body.description,
            league_timezone=body.league_timezone,
            rules=body.rules.model_dump() if body.rules is not None else None,
            initial_players=list(body.initial_players),
        )
    )
    return CreateLeagueResponse(league_id=result.league_id, host_token=result.host_token)


@router.get("/leagues", status_code=status.HTTP_200_OK, response_model=SearchLeaguesResponse)
async def search_leagues_by_title_prefix(
    title_prefix: str = Query(..., description="Prefix of league title; matched case-insensitively after trim"),
    limit: int = Query(
        SearchLeaguesByTitlePrefixUseCase.DEFAULT_LIMIT,
        ge=1,
        description=f"Maximum leagues to return (capped at {SearchLeaguesByTitlePrefixUseCase.MAX_LIMIT})",
    ),
    use_case: SearchLeaguesByTitlePrefixUseCase = Depends(get_search_leagues_by_title_prefix_use_case),
) -> SearchLeaguesResponse:
    normalized = title_prefix.strip().lower()
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="title_prefix must not be blank",
        )
    items = await use_case.execute(
        SearchLeaguesByTitlePrefixQuery(title_prefix_normalized=normalized, limit=limit)
    )
    return SearchLeaguesResponse(
        leagues=[LeagueListItemSchema(league_id=i.league_id, title=i.title) for i in items]
    )


@router.post(
    "/leagues/{league_id}/matches",
    status_code=status.HTTP_201_CREATED,
    response_model=SubmitMatchResultResponse,
)
@limiter.limit("30/minute")
async def submit_match_result(
    request: Request,
    league_id: str,
    body: SubmitMatchResultRequest,
    use_case: SubmitMatchResultUseCase = Depends(get_submit_match_result_use_case),
) -> SubmitMatchResultResponse:
    result = await use_case.execute(
        SubmitMatchResultCommand(
            league_id=league_id,
            team1_nicknames=(body.team1_nicknames[0], body.team1_nicknames[1]),
            team2_nicknames=(body.team2_nicknames[0], body.team2_nicknames[1]),
            team1_score=body.team1_score,
            team2_score=body.team2_score,
        )
    )
    return SubmitMatchResultResponse(
        match_id=result.match_id,
        created_at=result.created_at,
    )


@router.patch(
    "/leagues/{league_id}/matches/{match_id}",
    status_code=status.HTTP_200_OK,
    response_model=EditMatchScoreResponse,
)
@limiter.limit("60/minute")
async def edit_match_score_by_player(
    request: Request,
    league_id: str,
    match_id: str,
    body: EditMatchScoreRequest,
    use_case: EditMatchScoreUseCase = Depends(get_edit_match_score_use_case),
) -> EditMatchScoreResponse:
    """Player-facing match score edit.

    Open to anyone with `league_id` (no `X-Host-Token`), but only while
    the match is within the configured player-edit window
    (`PLAYER_SCORE_EDIT_WINDOW_SECONDS`, default 3600s). Outside the
    window the request 422s with `MatchEditWindowExpiredError` and the
    caller must ask the host to edit it via the admin endpoint.

    The admin endpoint at `PATCH /admin/leagues/{id}/matches/{id}`
    (requires `X-Host-Token`) remains unchanged and is **not** gated by
    the window.
    """
    result = await use_case.execute(
        EditMatchScoreCommand(
            host_token=None,
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
async def delete_match_by_player(
    request: Request,
    league_id: str,
    match_id: str,
    use_case: DeleteMatchUseCase = Depends(get_delete_match_use_case),
) -> None:
    """Player-facing match delete.

    Open to anyone with `league_id` (no `X-Host-Token`), but only while
    the match is within the configured player-delete window
    (`PLAYER_MATCH_DELETE_WINDOW_SECONDS`, default 600s). Outside the
    window the request 422s with `MatchDeleteWindowExpiredError` and the
    caller must ask the host to delete it via the admin endpoint.

    The admin endpoint at `DELETE /admin/leagues/{id}/matches/{id}`
    (requires `X-Host-Token`) remains unchanged and is **not** gated by
    the window.
    """
    await use_case.execute(
        DeleteMatchCommand(
            host_token=None,
            league_id=league_id,
            match_id=match_id,
        )
    )


@router.get(
    "/leagues/{league_id}/standings",
    status_code=status.HTTP_200_OK,
    response_model=GetStandingsResponse,
)
async def get_standings(
    league_id: str,
    start_date: date | None = Query(
        None, description="Inclusive league-local start date (YYYY-MM-DD)"
    ),
    end_date: date | None = Query(
        None, description="Inclusive league-local end date (YYYY-MM-DD)"
    ),
    use_case: GetStandingsUseCase = Depends(get_get_standings_use_case),
) -> GetStandingsResponse:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be before or equal to end_date",
        )
    view = await use_case.execute(
        GetStandingsQuery(league_id=league_id, start_date=start_date, end_date=end_date)
    )
    return GetStandingsResponse(
        standings=[_to_standings_entry_schema(e) for e in view.entries],
        tie_breakers=list(view.tie_breakers),
    )


@router.get(
    "/leagues/{league_id}/standings/by-player",
    status_code=status.HTTP_200_OK,
    response_model=GetStandingsResponse,
)
async def get_standings_by_player(
    league_id: str,
    player_name: str = Query(..., description="Player nickname (case-insensitive)"),
    start_date: date | None = Query(
        None, description="Inclusive league-local start date (YYYY-MM-DD)"
    ),
    end_date: date | None = Query(
        None, description="Inclusive league-local end date (YYYY-MM-DD)"
    ),
    use_case: GetStandingsByPlayerUseCase = Depends(get_get_standings_by_player_use_case),
) -> GetStandingsResponse:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="start_date must be before or equal to end_date",
        )
    view = await use_case.execute(
        GetStandingsByPlayerQuery(
            league_id=league_id,
            player_name=player_name,
            start_date=start_date,
            end_date=end_date,
        )
    )
    return GetStandingsResponse(
        standings=[_to_standings_entry_schema(e) for e in view.entries],
        tie_breakers=list(view.tie_breakers),
    )


def _to_standings_entry_schema(entry) -> StandingsEntrySchema:
    return StandingsEntrySchema(
        subject_kind=entry.subject_kind,
        rank=entry.rank,
        matches_played=entry.matches_played,
        wins=entry.wins,
        losses=entry.losses,
        games_won=entry.games_won,
        games_lost=entry.games_lost,
        games_diff=entry.games_diff,
        win_pct=entry.win_pct,
        draws=entry.draws,
        team_id=entry.team_id,
        player1_nickname=entry.player1_nickname,
        player2_nickname=entry.player2_nickname,
        player_id=entry.player_id,
        nickname=entry.nickname,
    )


@router.get(
    "/leagues/{league_id}/matches",
    status_code=status.HTTP_200_OK,
    response_model=GetMatchHistoryResponse,
)
async def get_match_history(
    league_id: str,
    use_case: GetMatchHistoryUseCase = Depends(get_get_match_history_use_case),
) -> GetMatchHistoryResponse:
    records = await use_case.execute(GetMatchHistoryQuery(league_id=league_id))
    return GetMatchHistoryResponse(
        matches=[
            MatchHistoryRecordSchema(
                match_id=r.match_id,
                team1_player1_nickname=r.team1_player1_nickname,
                team1_player2_nickname=r.team1_player2_nickname,
                team2_player1_nickname=r.team2_player1_nickname,
                team2_player2_nickname=r.team2_player2_nickname,
                team1_score=r.team1_score,
                team2_score=r.team2_score,
                created_at=r.created_at,
            )
            for r in records
        ]
    )


@router.get(
    "/leagues/{league_id}/matches/by-player",
    status_code=status.HTTP_200_OK,
    response_model=GetMatchHistoryResponse,
)
async def get_match_history_by_player(
    league_id: str,
    player_name: str = Query(..., description="Player nickname (case-insensitive)"),
    use_case: GetMatchHistoryByPlayerUseCase = Depends(get_get_match_history_by_player_use_case),
) -> GetMatchHistoryResponse:
    records = await use_case.execute(
        GetMatchHistoryByPlayerQuery(league_id=league_id, player_name=player_name)
    )
    return GetMatchHistoryResponse(
        matches=[
            MatchHistoryRecordSchema(
                match_id=r.match_id,
                team1_player1_nickname=r.team1_player1_nickname,
                team1_player2_nickname=r.team1_player2_nickname,
                team2_player1_nickname=r.team2_player1_nickname,
                team2_player2_nickname=r.team2_player2_nickname,
                team1_score=r.team1_score,
                team2_score=r.team2_score,
                created_at=r.created_at,
            )
            for r in records
        ]
    )


@router.get(
    "/leagues/{league_id}/roster",
    status_code=status.HTTP_200_OK,
    response_model=GetLeagueRosterResponse,
)
async def get_league_roster(
    league_id: str,
    use_case: GetLeagueRosterUseCase = Depends(get_get_league_roster_use_case),
) -> GetLeagueRosterResponse:
    roster = await use_case.execute(GetLeagueRosterQuery(league_id=league_id))
    return GetLeagueRosterResponse(
        title=roster.title,
        league_timezone=roster.league_timezone,
        latest_match_date=roster.latest_match_date,
        rules=LeagueRulesResponseSchema(**roster.rules),
        players=[
            PlayerEntrySchema(
                player_id=p.player_id,
                nickname=p.nickname,
                teams_count=p.teams_count,
                matches_count=p.matches_count,
            )
            for p in roster.players
        ],
        teams=[
            TeamEntrySchema(
                team_id=t.team_id,
                player1_nickname=t.player1_nickname,
                player2_nickname=t.player2_nickname,
            )
            for t in roster.teams
        ],
        player_score_edit_window_seconds=player_score_edit_window_seconds(),
        player_match_delete_window_seconds=player_match_delete_window_seconds(),
    )
