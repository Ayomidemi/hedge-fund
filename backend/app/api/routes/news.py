from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.news import (
    NewsOverviewResponse,
    NewsPollRequest,
    NewsPollRunResponse,
    NewsTickerRefreshRequest,
)
from app.core.auth import AuthenticatedUser, require_authenticated_user
from app.db.session import get_session
from app.services.news.centre import (
    NewsUnavailableError,
    build_news_overview,
    news_run_response,
    poll_news,
    refresh_ticker_news,
)
from app.services.realtime.events import news_poll_completed_event
from app.services.realtime.redis_bus import publish_event

router = APIRouter(prefix="/news")


@router.get("/overview", response_model=NewsOverviewResponse)
async def read_news_overview(
    ticker: str | None = Query(default=None),
    market: str | None = Query(default=None),
    jurisdiction: str | None = Query(default="all"),
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> NewsOverviewResponse:
    return await build_news_overview(
        session,
        ticker=ticker,
        market=_market(market),
        jurisdiction=jurisdiction,
        owner_user_id=user.id,
    )


@router.post("/poll", response_model=NewsPollRunResponse)
async def create_news_poll(
    payload: NewsPollRequest | None = None,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> NewsPollRunResponse:
    _ = user
    request = payload or NewsPollRequest()
    run = await poll_news(
        session,
        trigger="manual",
        jurisdiction=request.jurisdiction,
        force=request.force,
    )
    await _publish_run(run)
    return news_run_response(run)


@router.post("/ticker/{ticker}/refresh", response_model=NewsPollRunResponse)
async def refresh_news_ticker(
    ticker: str,
    payload: NewsTickerRefreshRequest | None = None,
    session: AsyncSession = Depends(get_session),
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> NewsPollRunResponse:
    _ = user
    request = payload or NewsTickerRefreshRequest()
    try:
        run = await refresh_ticker_news(
            session,
            ticker=ticker,
            market=_market(request.market),
            force=request.force,
        )
    except NewsUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await _publish_run(run)
    return news_run_response(run)


async def _publish_run(run) -> None:
    await publish_event(
        news_poll_completed_event(
            run_id=str(run.id),
            status=run.status,
            trigger=run.trigger,
            target_scope=run.target_scope,
            target_key=run.target_key,
            provider_calls=run.provider_calls,
            items_seen=run.items_seen,
            items_created=run.items_created,
            items_updated=run.items_updated,
            cache_hit=run.cache_hit,
        )
    )


def _market(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    if normalized in {"US", "NG"}:
        return normalized
    return None
