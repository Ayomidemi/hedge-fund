from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.market_radar import (
    MarketRadarOverviewResponse,
    MarketRadarRunResponse,
    MarketRadarScanRequest,
    RadarWatchlistChartResponse,
    RadarWatchlistCreateRequest,
    RadarWatchlistDetailResponse,
    RadarWatchlistItemResponse,
    RadarWatchlistListResponse,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.market_radar.overview import build_radar_overview
from app.services.market_radar.scan import run_radar_scan
from app.services.market_radar.watchlist_book import (
    WatchlistNotFoundError,
    WatchlistValidationError,
    add_watchlist_item,
    get_watchlist_chart,
    get_watchlist_detail,
    list_watchlist,
    remove_watchlist_item,
)

router = APIRouter(prefix="/market-radar")


@router.get("/overview", response_model=MarketRadarOverviewResponse)
async def read_market_radar_overview(
    jurisdiction: str | None = Query(default="all"),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MarketRadarOverviewResponse:
    normalized = (jurisdiction or "all").upper()
    if normalized == "ALL":
        normalized = "all"
    return await build_radar_overview(
        session,
        jurisdiction=normalized if normalized in {"US", "NG", "all"} else "all",
        owner_user_id=user.id,
    )


@router.post("/scan", response_model=MarketRadarRunResponse)
async def create_market_radar_scan(
    payload: MarketRadarScanRequest | None = None,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MarketRadarRunResponse:
    request = payload or MarketRadarScanRequest()
    run = await run_radar_scan(
        session,
        jurisdictions=request.jurisdictions,
        force=request.force,
        triggered_by_user_id=user.id,
    )
    return MarketRadarRunResponse(
        id=run.id,
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status,
        triggered_by_user_id=run.triggered_by_user_id,
        jurisdictions_requested=list(run.jurisdictions_requested or []),
        jurisdictions_scanned=list(run.jurisdictions_scanned or []),
        jurisdictions_skipped=list(run.jurisdictions_skipped or []),
        vendor_calls=run.vendor_calls,
        cache_hits=run.cache_hits,
        catalog_count=run.catalog_count,
        working_set_count=run.working_set_count,
        flagged_count=run.flagged_count,
        promoted_count=run.promoted_count,
        promotion_owner_ids=list(run.promotion_owner_ids or []),
        notes=list(run.notes or []),
        errors=list(run.errors or []),
    )


@router.get("/watchlist", response_model=RadarWatchlistListResponse)
async def read_radar_watchlist(
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RadarWatchlistListResponse:
    return await list_watchlist(session, owner_user_id=user.id)


@router.post(
    "/watchlist",
    response_model=RadarWatchlistItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_radar_watchlist_item(
    payload: RadarWatchlistCreateRequest,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RadarWatchlistItemResponse:
    try:
        return await add_watchlist_item(
            session, owner_user_id=user.id, payload=payload
        )
    except WatchlistValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/watchlist/{ticker}/chart", response_model=RadarWatchlistChartResponse)
async def read_radar_watchlist_chart(
    ticker: str,
    range: str = Query(default="1d"),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RadarWatchlistChartResponse:
    try:
        return await get_watchlist_chart(
            session,
            owner_user_id=user.id,
            ticker=ticker,
            range_key=range,
        )
    except WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except WatchlistValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/watchlist/{ticker}", response_model=RadarWatchlistDetailResponse)
async def read_radar_watchlist_ticker(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> RadarWatchlistDetailResponse:
    try:
        return await get_watchlist_detail(
            session, owner_user_id=user.id, ticker=ticker
        )
    except WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.delete("/watchlist/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_radar_watchlist_item(
    ticker: str,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> None:
    try:
        await remove_watchlist_item(
            session, owner_user_id=user.id, ticker=ticker
        )
    except WatchlistNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
