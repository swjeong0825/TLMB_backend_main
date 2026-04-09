from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.schemas.league_schemas import (
    CreateLeagueRequest,
    CreateLeagueResponse,
    GetLeagueRosterResponse,
    GetMatchHistoryResponse,
    GetStandingsResponse,
    MatchHistoryRecordSchema,
    PlayerEntrySchema,
    StandingsEntrySchema,
    LeagueListItemSchema,
    SearchLeaguesResponse,
    SubmitMatchResultRequest,
    SubmitMatchResultResponse,
    TeamEntrySchema,
)
from app.application.use_cases.create_league_use_case import (
    CreateLeagueCommand,
    CreateLeagueUseCase,
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
    get_get_league_roster_use_case,
    get_get_match_history_by_player_use_case,
    get_get_match_history_use_case,
    get_get_standings_by_player_use_case,
    get_get_standings_use_case,
    get_search_leagues_by_title_prefix_use_case,
    get_submit_match_result_use_case,
)

router = APIRouter(tags=["leagues"])


@router.post("/leagues", status_code=status.HTTP_201_CREATED, response_model=CreateLeagueResponse)
async def create_league(
    body: CreateLeagueRequest,
    use_case: CreateLeagueUseCase = Depends(get_create_league_use_case),
) -> CreateLeagueResponse:
    result = await use_case.execute(
        CreateLeagueCommand(
            title=body.title,
            description=body.description,
            rules=body.rules.model_dump() if body.rules is not None else None,
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
async def submit_match_result(
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
    return SubmitMatchResultResponse(match_id=result.match_id)


@router.get(
    "/leagues/{league_id}/standings",
    status_code=status.HTTP_200_OK,
    response_model=GetStandingsResponse,
)
async def get_standings(
    league_id: str,
    use_case: GetStandingsUseCase = Depends(get_get_standings_use_case),
) -> GetStandingsResponse:
    entries = await use_case.execute(GetStandingsQuery(league_id=league_id))
    return GetStandingsResponse(
        standings=[
            StandingsEntrySchema(
                rank=e.rank,
                team_id=e.team_id,
                player1_nickname=e.player1_nickname,
                player2_nickname=e.player2_nickname,
                wins=e.wins,
                losses=e.losses,
            )
            for e in entries
        ]
    )


@router.get(
    "/leagues/{league_id}/standings/by-player",
    status_code=status.HTTP_200_OK,
    response_model=GetStandingsResponse,
)
async def get_standings_by_player(
    league_id: str,
    player_name: str = Query(..., description="Player nickname (case-insensitive)"),
    use_case: GetStandingsByPlayerUseCase = Depends(get_get_standings_by_player_use_case),
) -> GetStandingsResponse:
    entries = await use_case.execute(
        GetStandingsByPlayerQuery(league_id=league_id, player_name=player_name)
    )
    return GetStandingsResponse(
        standings=[
            StandingsEntrySchema(
                rank=e.rank,
                team_id=e.team_id,
                player1_nickname=e.player1_nickname,
                player2_nickname=e.player2_nickname,
                wins=e.wins,
                losses=e.losses,
            )
            for e in entries
        ]
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
        players=[PlayerEntrySchema(player_id=p.player_id, nickname=p.nickname) for p in roster.players],
        teams=[
            TeamEntrySchema(
                team_id=t.team_id,
                player1_nickname=t.player1_nickname,
                player2_nickname=t.player2_nickname,
            )
            for t in roster.teams
        ],
    )
