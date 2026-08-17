from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.market_radar import (
    MarketRadarOverviewResponse,
    MarketRadarRunResponse,
    MarketRadarScanRequest,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.market_radar.overview import build_radar_overview
from app.services.market_radar.scan import run_radar_scan

router = APIRouter(prefix="/market-radar")


@router.get("/overview", response_model=MarketRadarOverviewResponse)
async def read_market_radar_overview(
    jurisdiction: str | None = Query(default="all"),
    session: AsyncSession = Depends(get_session),
    _user: AuthenticatedUser = Depends(require_authenticated_user),
) -> MarketRadarOverviewResponse:
    normalized = (jurisdiction or "all").upper()
    if normalized == "ALL":
        normalized = "all"
    return await build_radar_overview(
        session,
        jurisdiction=normalized if normalized in {"US", "NG", "all"} else "all",
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
