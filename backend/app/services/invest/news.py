from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.schemas.invest import (
    InvestNewsItemResponse,
    InvestNewsOverviewResponse,
    InvestNewsPaginationResponse,
)
from app.core.auth import AuthenticatedUser
from app.models import Instrument, NewsItem, NewsItemStar, RetailWatchlistItem
from app.services.invest import accounts as invest_accounts
from app.services.invest.fixed_income import (
    FIXED_INCOME_PRODUCTS,
    get_fixed_income_product,
    get_fixed_income_product_db,
    search_fixed_income_products_db,
)
from app.services.invest.markets import active_board_tickers, rates_board_tickers
from app.services.news import centre as news_centre
from app.services.news.providers import _fetch_tiingo_news, normalize_ticker

logger = logging.getLogger(__name__)

FOR_YOU_LIMIT = 8
SECTION_LIMIT = 8
INCOME_LIMIT = 8
INCOME_POOL = 80
HEADLINES_DEFAULT_PAGE_SIZE = 10
TICKER_PAGE_SIZE = 8
SAVED_PAGE_SIZE = 8
INCOME_REFRESH_MIN_ITEMS = 5
INCOME_REFRESH_TIMEOUT_SECONDS = 6.0

US_INCOME_KEYWORDS = (
    "treasury",
    "treasuries",
    "t-bill",
    "t bill",
    "tbill",
    "t-note",
    "t-bond",
    "yield curve",
    "bond yield",
    "treasury yield",
    "fed funds",
    "rate cut",
    "rate hike",
    "duration risk",
    "money market",
    "fomc",
)
NG_INCOME_KEYWORDS = (
    "fgn",
    "cbn",
    "naira",
    "dmo",
    "fmdq",
    "nigerian treasury",
    "nigeria treasury",
    "ntb",
    "treasury bill",
    "bond auction",
    "open market operation",
)


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
    income_page: int = 1,
    income_page_size: int = INCOME_LIMIT,
    for_you_page: int = 1,
    for_you_page_size: int = FOR_YOU_LIMIT,
    markets_page: int = 1,
    markets_page_size: int = SECTION_LIMIT,
    saved_page: int = 1,
    saved_page_size: int = SAVED_PAGE_SIZE,
) -> InvestNewsOverviewResponse:
    generated_at = datetime.now(timezone.utc)
    income_tickers = await income_proxy_tickers_db(session)
    income_ticker_set = set(income_tickers)
    portfolio_tickers = await _portfolio_news_tickers(session, user)
    watchlist_tickers = await _retail_watchlist_news_tickers(session, user.id)
    active_board = await active_board_tickers(session)
    listed_board = [
        symbol for symbol in active_board if symbol not in income_ticker_set
    ]
    for_you_tickers = _unique([*portfolio_tickers, *watchlist_tickers])
    normalized_jurisdiction = news_centre._normalize_jurisdiction(jurisdiction)

    current_page = max(page, 1)
    current_page_size = min(max(page_size, 5), news_centre.CURRENT_NEWS_MAX_PAGE_SIZE)
    headlines, headlines_total = await news_centre._current_items(
        session,
        jurisdiction=normalized_jurisdiction,
        page=current_page,
        page_size=current_page_size,
    )
    income_window, _ = await news_centre._current_items(
        session,
        jurisdiction=normalized_jurisdiction,
        page=1,
        page_size=INCOME_POOL,
    )
    ticker_income, _ = await news_centre._items_for_tickers(
        session, income_tickers, page=1, page_size=INCOME_POOL
    )
    income_pool = _merge_income_stories(
        ticker_income,
        income_window,
        jurisdiction=normalized_jurisdiction,
        income_ticker_set=income_ticker_set,
        limit=INCOME_POOL,
    )
    selected_income_page = max(income_page, 1)
    selected_income_page_size = min(max(income_page_size, 5), 20)
    income_items, income_total = _slice_page(
        income_pool, selected_income_page, selected_income_page_size
    )
    selected_for_you_page = max(for_you_page, 1)
    selected_for_you_page_size = min(max(for_you_page_size, 5), 20)
    for_you_items, for_you_total = await news_centre._items_for_tickers(
        session,
        for_you_tickers,
        page=selected_for_you_page,
        page_size=selected_for_you_page_size,
    )
    selected_markets_page = max(markets_page, 1)
    selected_markets_page_size = min(max(markets_page_size, 5), 20)
    markets_items, markets_total = await news_centre._items_for_tickers(
        session,
        listed_board,
        page=selected_markets_page,
        page_size=selected_markets_page_size,
    )
    selected_saved_page = max(saved_page, 1)
    selected_saved_page_size = min(max(saved_page_size, 5), 20)
    saved_items, saved_total = await _saved_news_page(
        session,
        user.id,
        page=selected_saved_page,
        page_size=selected_saved_page_size,
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
            *(item.id for item in income_items),
            *(item.id for item in for_you_items),
            *(item.id for item in markets_items),
            *(item.id for item in headlines),
            *(item.id for item in ticker_items),
            *(item.id for item in saved_items),
        ],
    )

    return InvestNewsOverviewResponse(
        generated_at=generated_at,
        summary=_summary(
            income_count=income_total,
            portfolio_count=len(portfolio_tickers),
            watchlist_count=len(watchlist_tickers),
        ),
        portfolio_tickers=portfolio_tickers,
        watchlist_tickers=watchlist_tickers,
        markets_tickers=listed_board,
        for_you=[_item_response(item, starred_ids) for item in for_you_items],
        markets_items=[_item_response(item, starred_ids) for item in markets_items],
        income_tickers=income_tickers,
        income_items=[_item_response(item, starred_ids) for item in income_items],
        headlines=[_item_response(item, starred_ids) for item in headlines],
        headlines_page=_pagination(current_page, current_page_size, headlines_total),
        income_page=_pagination(
            selected_income_page, selected_income_page_size, income_total
        ),
        for_you_page=_pagination(
            selected_for_you_page, selected_for_you_page_size, for_you_total
        ),
        markets_page=_pagination(
            selected_markets_page, selected_markets_page_size, markets_total
        ),
        ticker=normalized_ticker,
        ticker_items=[_item_response(item, starred_ids) for item in ticker_items],
        ticker_page=(
            _pagination(selected_ticker_page, selected_ticker_page_size, ticker_total)
            if normalized_ticker
            else None
        ),
        saved_items=[_item_response(item, starred_ids) for item in saved_items],
        saved_page=_pagination(selected_saved_page, selected_saved_page_size, saved_total),
    )


def _pagination(page: int, page_size: int, total: int) -> InvestNewsPaginationResponse:
    current = max(page, 1)
    size = max(page_size, 1)
    return InvestNewsPaginationResponse(
        page=current,
        page_size=size,
        total=total,
        has_next=current * size < total,
        has_previous=current > 1,
    )


def _slice_page(
    items: list[NewsItem], page: int, page_size: int
) -> tuple[list[NewsItem], int]:
    total = len(items)
    start = (max(page, 1) - 1) * max(page_size, 1)
    return items[start : start + max(page_size, 1)], total


async def _saved_news_page(
    session: AsyncSession,
    user_id: str | None,
    *,
    page: int,
    page_size: int,
) -> tuple[list[NewsItem], int]:
    if not user_id:
        return [], 0
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(NewsItemStar)
            .where(NewsItemStar.owner_user_id == user_id)
        )
        or 0
    )
    items = list(
        await session.scalars(
            select(NewsItem)
            .join(NewsItemStar, NewsItemStar.news_item_id == NewsItem.id)
            .options(selectinload(NewsItem.ticker_links))
            .where(NewsItemStar.owner_user_id == user_id)
            .order_by(NewsItemStar.created_at.desc())
            .offset((max(page, 1) - 1) * max(page_size, 1))
            .limit(max(page_size, 1))
        )
    )
    return items, total


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


def income_proxy_tickers() -> list[str]:
    tickers = list(rates_board_tickers())
    for product in FIXED_INCOME_PRODUCTS:
        tickers.append(product.ticker)
        if product.proxy_ticker:
            tickers.append(product.proxy_ticker)
    return _unique(tickers)


INCOME_TICKERS = income_proxy_tickers()
INCOME_TICKER_SET = set(INCOME_TICKERS)


async def income_proxy_tickers_db(session: AsyncSession) -> list[str]:
    tickers = list(rates_board_tickers())
    for product in await search_fixed_income_products_db(session):
        tickers.append(product.ticker)
        if product.proxy_ticker:
            tickers.append(product.proxy_ticker)
    return _unique(tickers)


def is_income_story(
    *,
    title: str,
    summary: str | None,
    tickers: list[str],
    jurisdiction: str | None = None,
    income_ticker_set: set[str] | None = None,
) -> bool:
    income_ticker_set = income_ticker_set or INCOME_TICKER_SET
    ticker_set = {ticker.upper() for ticker in tickers if ticker}
    if ticker_set & income_ticker_set:
        return True
    text = f"{title} {summary or ''}".lower()
    return any(keyword in text for keyword in _keywords_for(jurisdiction))


async def _refresh_income_news_if_needed(
    session: AsyncSession, tickers: list[str]
) -> None:
    fixed_income_tickers = {
        product.ticker for product in await search_fixed_income_products_db(session)
    }
    listed_proxies = [
        ticker
        for ticker in tickers
        if ticker.upper() not in fixed_income_tickers and not ticker.endswith(".NG")
    ]
    _, total = await news_centre._items_for_tickers(
        session, listed_proxies, page=1, page_size=INCOME_LIMIT
    )
    if total >= INCOME_REFRESH_MIN_ITEMS or not listed_proxies:
        return
    try:
        result = await asyncio.wait_for(
            _fetch_tiingo_news(listed_proxies),
            timeout=INCOME_REFRESH_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        logger.warning("invest_income_news_refresh_timed_out")
        return
    except Exception:
        logger.warning("invest_income_news_refresh_failed", exc_info=True)
        return
    if result.items:
        await news_centre._upsert_provider_items(session, result.items)


def _merge_income_stories(
    ticker_items: list[NewsItem],
    window: list[NewsItem],
    *,
    jurisdiction: str | None,
    limit: int,
    income_ticker_set: set[str] | None = None,
) -> list[NewsItem]:
    merged: list[NewsItem] = []
    seen: set[UUID] = set()
    for item in [*ticker_items, *window]:
        if item.id in seen:
            continue
        tickers = [link.ticker for link in (item.ticker_links or [])]
        if not is_income_story(
            title=item.title,
            summary=item.summary,
            tickers=tickers,
            jurisdiction=jurisdiction,
            income_ticker_set=income_ticker_set,
        ):
            continue
        seen.add(item.id)
        merged.append(item)
        if len(merged) >= limit:
            break
    return merged


def _keywords_for(jurisdiction: str | None) -> tuple[str, ...]:
    if jurisdiction == "US":
        return US_INCOME_KEYWORDS
    if jurisdiction == "NG":
        return NG_INCOME_KEYWORDS
    return US_INCOME_KEYWORDS + NG_INCOME_KEYWORDS


async def _portfolio_news_tickers(
    session: AsyncSession, user: AuthenticatedUser
) -> list[str]:
    holdings = await invest_accounts.list_positions(session, user)
    tickers: list[str] = []
    for holding in holdings:
        tickers.extend(await _news_tickers_for_symbol_db(session, holding.ticker))
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
        tickers.extend(await _news_tickers_for_symbol_db(session, instrument.ticker))
    return _unique(tickers)


async def _news_tickers_for_symbol_db(session: AsyncSession, symbol: str) -> list[str]:
    normalized = (symbol or "").strip().upper()
    if not normalized:
        return []
    tickers = [normalized]
    product = await get_fixed_income_product_db(session, normalized)
    if product is not None and product.proxy_ticker:
        tickers.append(product.proxy_ticker.upper())
    return tickers


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
    *,
    income_count: int,
    portfolio_count: int = 0,
    watchlist_count: int = 0,
    for_you_count: int = 0,
) -> str:
    _ = for_you_count
    if income_count:
        personal = ""
        if portfolio_count or watchlist_count:
            personal = " Personal holdings and watchlist follow after the rates tape."
        return (
            f"{income_count} rates and income headline"
            f"{'s' if income_count != 1 else ''} from Treasuries, bills, "
            f"FGN context, and listed duration proxies.{personal}"
        )
    if portfolio_count or watchlist_count:
        return (
            "No fresh rates headlines yet. Tracking your book below; "
            "Treasuries and bills stay the lead when Tiingo has copy."
        )
    return (
        "Rates and income lead this page — T-bills, Treasuries, FGN context, "
        "and listed proxies (BIL, SHY, IEF, TLT). Listed equity tape stays below."
    )


async def rates_headline(session: AsyncSession) -> str | None:
    items = await income_news_items(session, limit=1)
    return items[0].title if items else None


async def income_news_items(
    session: AsyncSession, *, limit: int = 5, jurisdiction: str | None = None
) -> list[NewsItem]:
    window, _ = await news_centre._current_items(
        session, jurisdiction=jurisdiction, page=1, page_size=40
    )
    ticker_income, _ = await news_centre._items_for_tickers(
        session, INCOME_TICKERS, page=1, page_size=limit
    )
    return _merge_income_stories(
        ticker_income, window, jurisdiction=jurisdiction, limit=limit
    )


async def latest_news_items(
    session: AsyncSession, *, limit: int = 8, jurisdiction: str | None = None
) -> list[NewsItem]:
    items, _ = await news_centre._current_items(
        session, jurisdiction=jurisdiction, page=1, page_size=limit
    )
    return items


async def headlines_for_tickers(
    session: AsyncSession, tickers: list[str]
) -> dict[str, str]:
    wanted = {ticker.upper() for ticker in tickers if ticker}
    if not wanted:
        return {}
    items, _ = await news_centre._items_for_tickers(
        session, list(wanted), page=1, page_size=min(max(len(wanted) * 2, 8), 40)
    )
    found: dict[str, str] = {}
    for item in items:
        for link in item.ticker_links or []:
            key = (link.ticker or "").upper()
            if key in wanted and key not in found:
                found[key] = item.title
        if len(found) >= len(wanted):
            break
    return found
