from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.invest import (
    InvestNewsItemResponse,
    InvestNewsOverviewResponse,
    InvestNewsPaginationResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import Instrument, RetailWatchlistItem
from app.services.invest import accounts as invest_accounts
from app.services.invest.fixed_income import get_fixed_income_product
from app.services.invest.markets import board_tickers
from app.services.news import centre as news_centre
from app.services.news.providers import normalize_ticker

FOR_YOU_LIMIT = 24
SECTION_LIMIT = 16
HEADLINES_DEFAULT_PAGE_SIZE = 20
TICKER_PAGE_SIZE = 8


async def build_invest_news_overview(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    ticker: str | None = None,
    market: str | None = None,
    jurisdiction: str | None = "all",
    page: int = 1,
    page_size: int = HEADLINES_DEFAULT_PAGE_SIZE,
    ticker_page: int = 1,
    ticker_page_size: int = TICKER_PAGE_SIZE,
) -> InvestNewsOverviewResponse:
    generated_at = datetime.now(timezone.utc)
    portfolio_tickers = await _portfolio_news_tickers(session, user)
    watchlist_tickers = await _retail_watchlist_news_tickers(session, user.id)
    markets = list(board_tickers())
    for_you_tickers = _unique([*portfolio_tickers, *watchlist_tickers])

    headlines, headlines_total = await news_centre._current_items(
        session,
        jurisdiction=news_centre._normalize_jurisdiction(jurisdiction),
        page=max(page, 1),
        page_size=min(max(page_size, 5), news_centre.CURRENT_NEWS_MAX_PAGE_SIZE),
    )
    portfolio_items, _ = await news_centre._items_for_tickers(
        session, portfolio_tickers, page=1, page_size=SECTION_LIMIT
    )
    watchlist_items, _ = await news_centre._items_for_tickers(
        session, watchlist_tickers, page=1, page_size=SECTION_LIMIT
    )
    for_you_items, _ = await news_centre._items_for_tickers(
        session, for_you_tickers, page=1, page_size=FOR_YOU_LIMIT
    )
    markets_items, _ = await news_centre._items_for_tickers(
        session, markets, page=1, page_size=SECTION_LIMIT
    )
    saved_items = await news_centre._saved_items(
        session, user.id, limit=news_centre.WATCHLIST_NEWS_LIMIT
    )

    normalized_ticker = normalize_ticker(ticker or "", market) if ticker else None
    selected_ticker_page = max(ticker_page, 1)
    selected_ticker_page_size = min(
        max(ticker_page_size, 5), news_centre.TICKER_NEWS_MAX_PAGE_SIZE
    )
    ticker_items, ticker_total = (
        await news_centre._items_for_tickers(
            session,
            [normalized_ticker],
            page=selected_ticker_page,
            page_size=selected_ticker_page_size,
        )
        if normalized_ticker
        else ([], 0)
    )

    starred_ids = await news_centre._starred_item_ids(
        session,
        user.id,
        [
            *(item.id for item in for_you_items),
            *(item.id for item in portfolio_items),
            *(item.id for item in watchlist_items),
            *(item.id for item in markets_items),
            *(item.id for item in headlines),
            *(item.id for item in ticker_items),
            *(item.id for item in saved_items),
        ],
    )

    current_page = max(page, 1)
    current_page_size = min(max(page_size, 5), news_centre.CURRENT_NEWS_MAX_PAGE_SIZE)

    return InvestNewsOverviewResponse(
        generated_at=generated_at,
        summary=_summary(
            portfolio_count=len(portfolio_tickers),
            watchlist_count=len(watchlist_tickers),
            for_you_count=len(for_you_items),
        ),
        portfolio_tickers=portfolio_tickers,
        watchlist_tickers=watchlist_tickers,
        markets_tickers=markets,
        for_you=[_item_response(item, starred_ids) for item in for_you_items],
        portfolio_items=[_item_response(item, starred_ids) for item in portfolio_items],
        watchlist_items=[_item_response(item, starred_ids) for item in watchlist_items],
        markets_items=[_item_response(item, starred_ids) for item in markets_items],
        headlines=[_item_response(item, starred_ids) for item in headlines],
        headlines_page=InvestNewsPaginationResponse(
            page=current_page,
            page_size=current_page_size,
            total=headlines_total,
            has_next=current_page * current_page_size < headlines_total,
            has_previous=current_page > 1,
        ),
        ticker=normalized_ticker,
        ticker_items=[_item_response(item, starred_ids) for item in ticker_items],
        ticker_page=(
            InvestNewsPaginationResponse(
                page=selected_ticker_page,
                page_size=selected_ticker_page_size,
                total=ticker_total,
                has_next=selected_ticker_page * selected_ticker_page_size < ticker_total,
                has_previous=selected_ticker_page > 1,
            )
            if normalized_ticker
            else None
        ),
        saved_items=[_item_response(item, starred_ids) for item in saved_items],
    )


async def _portfolio_news_tickers(
    session: AsyncSession, user: AuthenticatedUser
) -> list[str]:
    holdings = await invest_accounts.list_positions(session, user)
    tickers: list[str] = []
    for holding in holdings:
        tickers.extend(_news_tickers_for_symbol(holding.ticker))
    return _unique(tickers)


async def _retail_watchlist_news_tickers(
    session: AsyncSession, user_id: str
) -> list[str]:
    rows = await session.scalars(
        select(RetailWatchlistItem)
        .options(selectinload(RetailWatchlistItem.instrument))
        .where(RetailWatchlistItem.user_id == user_id)
        .order_by(RetailWatchlistItem.date_added.desc())
    )
    tickers: list[str] = []
    for row in rows:
        instrument: Instrument | None = row.instrument
        if instrument is None:
            continue
        tickers.extend(_news_tickers_for_symbol(instrument.ticker))
    return _unique(tickers)


def _news_tickers_for_symbol(symbol: str) -> list[str]:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return []
    tickers = [normalized]
    product = get_fixed_income_product(normalized)
    if product is not None and product.proxy_ticker:
        tickers.append(product.proxy_ticker.upper())
    return tickers


def _item_response(item, starred_ids: set) -> InvestNewsItemResponse:
    base = news_centre._item_response(item, starred_ids=starred_ids)
    return InvestNewsItemResponse.model_validate(base.model_dump())


def _summary(
    *, portfolio_count: int, watchlist_count: int, for_you_count: int
) -> str:
    if portfolio_count or watchlist_count:
        parts = []
        if portfolio_count:
            parts.append(
                f"{portfolio_count} holding{'s' if portfolio_count != 1 else ''}"
            )
        if watchlist_count:
            parts.append(
                f"{watchlist_count} watchlist name{'s' if watchlist_count != 1 else ''}"
            )
        focus = " and ".join(parts)
        if for_you_count:
            return (
                f"Headlines tied to {focus}, plus market tape from the Invest boards."
            )
        return (
            f"Tracking {focus}. Add names or take positions to personalize this feed; "
            "market board headlines stay available below."
        )
    return (
        "Market headlines for the Invest boards. Add watchlist names or build a "
        "portfolio to personalize what shows first."
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        key = (value or "").strip().upper()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered
