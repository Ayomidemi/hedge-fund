from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestFixedIncomeProductResponse,
    InvestMarketBoardResponse,
    InvestMarketQuoteResponse,
    InvestMarketSessionResponse,
    InvestMarketsResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.models import Instrument, InstrumentQuote
from app.services.invest.fixed_income import (
    fixed_income_response,
    search_fixed_income_products,
)
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.quote_provider import fetch_quotes
from app.services.market_data.sessions import (
    ALL_JURISDICTIONS,
    jurisdiction_for_ticker,
    session_for,
)
from app.services.portfolio.operating_core import upsert_instrument


@dataclass(frozen=True)
class MarketBoardRow:
    ticker: str
    label: str
    name: str
    market: str
    group: str
    group_title: str
    group_description: str
    asset_class: str
    exchange: str
    currency: str
    sector: str


MARKET_BOARD: tuple[MarketBoardRow, ...] = (
    MarketBoardRow(
        "SPY", "S&P 500", "SPDR S&P 500 ETF", "US", "us_indices",
        "United States", "Listed index funds. Paper-tradable.",
        "etf", "ARCX", "USD", "Broad Market",
    ),
    MarketBoardRow(
        "QQQ", "Nasdaq", "Invesco QQQ Trust", "US", "us_indices",
        "United States", "Listed index funds. Paper-tradable.",
        "etf", "XNAS", "USD", "Technology",
    ),
    MarketBoardRow(
        "DIA", "Dow", "SPDR Dow Jones Industrial Average ETF", "US", "us_indices",
        "United States", "Listed index funds. Paper-tradable.",
        "etf", "ARCX", "USD", "Broad Market",
    ),
    MarketBoardRow(
        "IWM", "Small caps", "iShares Russell 2000 ETF", "US", "us_indices",
        "United States", "Listed index funds. Paper-tradable.",
        "etf", "ARCX", "USD", "Broad Market",
    ),
    MarketBoardRow(
        "BIL", "T-bills", "SPDR Bloomberg 1-3 Month T-Bill ETF", "US", "rates",
        "Rates proxies",
        "Listed funds that move with US rates. Use these beside the fixed-income shelf to compare ETF duration risk.",
        "etf", "ARCX", "USD", "Bonds",
    ),
    MarketBoardRow(
        "SHY", "Short Treasuries", "iShares 1-3 Year Treasury Bond ETF", "US", "rates",
        "Rates proxies",
        "Listed funds that move with US rates. Use these beside the fixed-income shelf to compare ETF duration risk.",
        "etf", "ARCX", "USD", "Bonds",
    ),
    MarketBoardRow(
        "IEF", "Intermediate Treasuries", "iShares 7-10 Year Treasury Bond ETF", "US", "rates",
        "Rates proxies",
        "Listed funds that move with US rates. Use these beside the fixed-income shelf to compare ETF duration risk.",
        "etf", "ARCX", "USD", "Bonds",
    ),
    MarketBoardRow(
        "TLT", "Long Treasuries", "iShares 20+ Year Treasury Bond ETF", "US", "rates",
        "Rates proxies",
        "Listed funds that move with US rates. Use these beside the fixed-income shelf to compare ETF duration risk.",
        "etf", "NASDAQ", "USD", "Bonds",
    ),
    MarketBoardRow(
        "XLK", "Technology", "Technology Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Technology",
    ),
    MarketBoardRow(
        "XLF", "Financials", "Financial Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Financial Services",
    ),
    MarketBoardRow(
        "XLE", "Energy", "Energy Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Energy",
    ),
    MarketBoardRow(
        "XLV", "Healthcare", "Health Care Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Healthcare",
    ),
    MarketBoardRow(
        "XLI", "Industrials", "Industrial Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Industrials",
    ),
    MarketBoardRow(
        "XLY", "Consumer", "Consumer Discretionary Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Consumer Cyclical",
    ),
    MarketBoardRow(
        "XLP", "Staples", "Consumer Staples Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Consumer Defensive",
    ),
    MarketBoardRow(
        "XLB", "Materials", "Materials Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Basic Materials",
    ),
    MarketBoardRow(
        "XLU", "Utilities", "Utilities Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Utilities",
    ),
    MarketBoardRow(
        "XLC", "Communication", "Communication Services Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Communication Services",
    ),
    MarketBoardRow(
        "XLRE", "Real estate", "Real Estate Select Sector SPDR", "US", "sectors",
        "US sectors", "Always-watched sector pulses from the shared tape.",
        "etf", "ARCX", "USD", "Real Estate",
    ),
    MarketBoardRow(
        "GTCO.NG", "Banking", "Guaranty Trust Holding", "NG", "nigeria",
        "Nigeria",
        "NGX has no listed ASI ETF here. These are liquid sector names used as market pulses.",
        "equity", "NGX", "NGN", "Banking",
    ),
    MarketBoardRow(
        "DANGCEM.NG", "Industrial", "Dangote Cement", "NG", "nigeria",
        "Nigeria",
        "NGX has no listed ASI ETF here. These are liquid sector names used as market pulses.",
        "equity", "NGX", "NGN", "Industrial",
    ),
    MarketBoardRow(
        "NESTLE.NG", "Consumer", "Nestle Nigeria", "NG", "nigeria",
        "Nigeria",
        "NGX has no listed ASI ETF here. These are liquid sector names used as market pulses.",
        "equity", "NGX", "NGN", "Consumer",
    ),
    MarketBoardRow(
        "SEPLAT.NG", "Oil & Gas", "Seplat Energy", "NG", "nigeria",
        "Nigeria",
        "NGX has no listed ASI ETF here. These are liquid sector names used as market pulses.",
        "equity", "NGX", "NGN", "Oil & Gas",
    ),
)


async def build_invest_markets(session: AsyncSession) -> InvestMarketsResponse:
    now = datetime.now(timezone.utc)
    sessions = []
    for item in ALL_JURISDICTIONS:
        state = session_for(item, now)
        sessions.append(
            InvestMarketSessionResponse(
                market=item,
                label=state.label,
                is_open=state.is_open,
            )
        )
    instruments = await _ensure_board_instruments(session)
    quotes = await _quotes_by_ticker(session, list(instruments.values()))
    await _fill_missing_quotes(session, instruments, quotes)
    quotes = await _quotes_by_ticker(session, list(instruments.values()))

    boards: dict[str, InvestMarketBoardResponse] = {}
    live_count = 0
    for row in MARKET_BOARD:
        instrument = instruments[row.ticker]
        quote = quotes.get(row.ticker)
        quote_status = _quote_status(quote, row.ticker, now)
        if quote_status == "live":
            live_count += 1
        board = boards.setdefault(
            row.group,
            InvestMarketBoardResponse(
                id=row.group,
                title=row.group_title,
                description=row.group_description,
                items=[],
            ),
        )
        board.items.append(
            InvestMarketQuoteResponse(
                ticker=row.ticker,
                label=row.label,
                name=instrument.name,
                market=row.market,
                group=row.group,
                trade_status="paper_tradable",
                currency=row.currency,
                price=quote.price if quote is not None else None,
                change_pct=quote.change_pct if quote is not None else None,
                as_of=quote.as_of if quote is not None else None,
                quote_status=quote_status,
                href=f"/invest/instruments/{row.ticker}",
            )
        )

    open_labels = [item.label for item in sessions if item.is_open]
    if open_labels:
        summary = (
            f"{', '.join(open_labels)}. {live_count} live marks on the board. "
            "Fixed-income products use modeled yield and settlement; listed funds show live or last-close market context."
        )
    else:
        summary = (
            "US and NGX cash sessions are closed. Showing last marks where we have them. "
            "Fixed-income products use modeled yield and settlement; listed funds show last-close market context."
        )

    return InvestMarketsResponse(
        generated_at=now,
        summary=summary,
        sessions=sessions,
        boards=list(boards.values()),
        fixed_income=[
            fixed_income_response(product) for product in search_fixed_income_products()
        ],
    )


def board_tickers() -> tuple[str, ...]:
    return tuple(row.ticker for row in MARKET_BOARD)


async def _ensure_board_instruments(
    session: AsyncSession,
) -> dict[str, Instrument]:
    tickers = [row.ticker for row in MARKET_BOARD]
    existing = {
        instrument.ticker: instrument
        for instrument in await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(tickers))
        )
    }
    for row in MARKET_BOARD:
        if row.ticker in existing:
            continue
        existing[row.ticker] = await upsert_instrument(
            session,
            InstrumentCreate(
                ticker=row.ticker,
                name=row.name,
                asset_class=row.asset_class,
                exchange=row.exchange,
                currency=row.currency,
                sector=row.sector,
                industry=row.group_title,
            ),
        )
    return existing


async def _quotes_by_ticker(
    session: AsyncSession, instruments: list[Instrument]
) -> dict[str, InstrumentQuote]:
    if not instruments:
        return {}
    ids = [instrument.id for instrument in instruments]
    by_id = {instrument.id: instrument.ticker for instrument in instruments}
    rows = await session.scalars(
        select(InstrumentQuote).where(InstrumentQuote.instrument_id.in_(ids))
    )
    return {by_id[row.instrument_id]: row for row in rows if row.instrument_id in by_id}


async def _fill_missing_quotes(
    session: AsyncSession,
    instruments: dict[str, Instrument],
    quotes: dict[str, InstrumentQuote],
) -> None:
    missing: list[str] = []
    for ticker, instrument in instruments.items():
        quote = quotes.get(ticker)
        if quote is not None and not quote.is_stale and quote.price > 0:
            continue
        if not session_for(jurisdiction_for_ticker(ticker)).allows_live_quotes:
            continue
        missing.append(instrument.ticker)
    if not missing:
        return
    fetched = await fetch_quotes(missing)
    if not fetched:
        return
    universe = {
        live.ticker: [instruments[live.ticker].id]
        for live in fetched.values()
        if live.ticker in instruments
    }
    if not universe:
        return
    await persist_quotes(session, universe, fetched, mark_missing_stale=False)
    await session.flush()


def _quote_status(
    quote: InstrumentQuote | None, ticker: str, now: datetime
) -> str:
    if quote is None or quote.price <= 0:
        return "unavailable"
    if quote.is_stale:
        return "last_close"
    if session_for(jurisdiction_for_ticker(ticker), now).is_open:
        return "live"
    return "last_close"
