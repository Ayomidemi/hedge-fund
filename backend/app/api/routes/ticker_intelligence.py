from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.ticker_intelligence import (
    TickerAnalysisCreate,
    TickerAnalysisResponse,
    TickerMemoResponse,
    TickerMemoSummaryResponse,
    TickerPrefillResponse,
)
from app.db.session import get_session
from app.services.ticker_intelligence.analysis import (
    analyze_ticker,
    list_recent_ticker_memos,
    list_ticker_memos,
)
from app.services.ticker_intelligence.market_data import (
    MarketDataUnavailableError,
    prefill_ticker,
)

router = APIRouter(prefix="/ticker-intelligence")


@router.post(
    "/analyze",
    response_model=TickerAnalysisResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticker_analysis(
    payload: TickerAnalysisCreate,
    session: AsyncSession = Depends(get_session),
) -> TickerAnalysisResponse:
    return await analyze_ticker(session, payload)


@router.get("/memos", response_model=list[TickerMemoSummaryResponse])
async def read_recent_ticker_memos(
    limit: int = Query(default=12, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
) -> list[TickerMemoSummaryResponse]:
    return await list_recent_ticker_memos(session, limit=limit)


@router.get("/{ticker}/prefill", response_model=TickerPrefillResponse)
async def read_ticker_prefill(ticker: str) -> TickerPrefillResponse:
    try:
        return await prefill_ticker(ticker)
    except MarketDataUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.get("/{ticker}/memos", response_model=list[TickerMemoResponse])
async def read_ticker_memos(
    ticker: str,
    session: AsyncSession = Depends(get_session),
) -> list[TickerMemoResponse]:
    return await list_ticker_memos(session, ticker)
