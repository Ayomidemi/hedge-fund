from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.invest import (
    InvestFixedIncomeProductResponse,
    InvestMarketBoardResponse,
    InvestMarketQuoteResponse,
    InvestMarketSessionResponse,
    InvestMarketsResponse,
)
from app.api.schemas.operating_core import InstrumentCreate
from app.models import Instrument, InstrumentQuote, InvestMarketBoardItem
from app.services.invest.fixed_income import (
    fixed_income_response_db,
    search_fixed_income_products_db,
)
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.quote_provider import fetch_quotes
from app.services.market_data.sessions import (
    ALL_JURISDICTIONS,
    jurisdiction_for_ticker,
    session_for,
)
from app.services.portfolio.operating_core import upsert_instrument

logger = logging.getLogger(__name__)

TIINGO_SUPPORTED_TICKERS_URL = (
    "https://apimedia.tiingo.com/docs/tiingo/daily/supported_tickers.zip"
)
TIINGO_SUPPORTED_TICKERS_TIMEOUT_SECONDS = 8.0


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
    exchange: str | None
    currency: str
    sector: str | None


DEFAULT_MARKET_BOARD_RULES: tuple[MarketBoardRow, ...] = (
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

    board_rows = await market_board_rows(session)
    instruments = await _ensure_board_instruments(session, board_rows)
    quotes = await _quotes_by_ticker(session, list(instruments.values()))
    await _fill_missing_quotes(session, instruments, quotes)
    quotes = await _quotes_by_ticker(session, list(instruments.values()))

    boards: dict[str, InvestMarketBoardResponse] = {}
    live_count = 0
    for row in board_rows:
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

    fixed_income = []
    for product in await search_fixed_income_products_db(session):
        fixed_income.append(await fixed_income_response_db(session, product))

    return InvestMarketsResponse(
        generated_at=now,
        summary=summary,
        sessions=sessions,
        boards=list(boards.values()),
        fixed_income=fixed_income,
    )


async def market_board_rows(session: AsyncSession) -> list[MarketBoardRow]:
    try:
        await _ensure_market_board_seed_rows(session)
        records = list(
            await session.scalars(
                select(InvestMarketBoardItem)
                .where(InvestMarketBoardItem.is_active.is_(True))
                .order_by(
                    InvestMarketBoardItem.display_order.asc(),
                    InvestMarketBoardItem.ticker.asc(),
                )
            )
        )
        if records:
            return [_board_row_from_record(record) for record in records]
    except ProgrammingError:
        logger.warning("invest_market_board_table_missing")
        await session.rollback()
    return list(DEFAULT_MARKET_BOARD_RULES)


async def active_board_tickers(session: AsyncSession) -> tuple[str, ...]:
    return tuple(row.ticker for row in await market_board_rows(session))


def board_tickers() -> tuple[str, ...]:
    """Default board tickers before tenant-specific DB state is available."""
    return tuple(row.ticker for row in DEFAULT_MARKET_BOARD_RULES)


def rates_board_tickers() -> tuple[str, ...]:
    return tuple(
        row.ticker for row in DEFAULT_MARKET_BOARD_RULES if row.group == "rates"
    )


async def _ensure_market_board_seed_rows(session: AsyncSession) -> None:
    default_tickers = [row.ticker for row in DEFAULT_MARKET_BOARD_RULES]
    existing = set(
        await session.scalars(
            select(InvestMarketBoardItem.ticker).where(
                InvestMarketBoardItem.ticker.in_(default_tickers)
            )
        )
    )
    missing = [
        (index, rule)
        for index, rule in enumerate(DEFAULT_MARKET_BOARD_RULES, start=1)
        if rule.ticker not in existing
    ]
    if not missing:
        return

    tiingo_metadata = await _tiingo_supported_metadata(
        [rule.ticker for _, rule in missing if rule.market == "US"]
    )
    now = datetime.now(timezone.utc)
    for index, rule in missing:
        session.add(
            _board_item_from_rule(
                rule,
                display_order=index * 10,
                tiingo_metadata=tiingo_metadata.get(rule.ticker),
                seeded_at=now,
            )
        )
    await session.flush()


def _board_item_from_rule(
    rule: MarketBoardRow,
    *,
    display_order: int,
    tiingo_metadata: dict | None,
    seeded_at: datetime,
) -> InvestMarketBoardItem:
    source = "tiingo_supported_tickers" if tiingo_metadata else "board_rule"
    return InvestMarketBoardItem(
        ticker=rule.ticker,
        label=rule.label,
        name=_first_metadata_text(tiingo_metadata, "name", "description") or rule.name,
        market=rule.market,
        board_group=rule.group,
        group_title=rule.group_title,
        group_description=rule.group_description,
        display_order=display_order,
        asset_class=(
            _asset_class_from_tiingo(tiingo_metadata.get("assetType"))
            if tiingo_metadata
            else rule.asset_class
        ),
        exchange=_first_metadata_text(tiingo_metadata, "exchange") or rule.exchange,
        currency=(
            _first_metadata_text(tiingo_metadata, "priceCurrency", "currency")
            or rule.currency
        ).upper(),
        sector=rule.sector,
        source=source,
        source_as_of=seeded_at if tiingo_metadata else None,
        source_metadata=_compact_tiingo_metadata(tiingo_metadata),
        is_active=True,
    )


def _board_row_from_record(record: InvestMarketBoardItem) -> MarketBoardRow:
    return MarketBoardRow(
        ticker=record.ticker,
        label=record.label,
        name=record.name,
        market=record.market,
        group=record.board_group,
        group_title=record.group_title,
        group_description=record.group_description,
        asset_class=record.asset_class,
        exchange=record.exchange,
        currency=record.currency,
        sector=record.sector,
    )


async def _tiingo_supported_metadata(tickers: list[str]) -> dict[str, dict]:
    wanted = {ticker.upper() for ticker in tickers}
    if not wanted:
        return {}

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(TIINGO_SUPPORTED_TICKERS_TIMEOUT_SECONDS)
        ) as client:
            response = await client.get(TIINGO_SUPPORTED_TICKERS_URL)
            response.raise_for_status()
        return _parse_tiingo_supported_tickers(response.content, wanted)
    except (httpx.HTTPError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        logger.warning(
            "tiingo_supported_tickers_seed_failed",
            extra={"error": str(exc)},
        )
        return {}


def _parse_tiingo_supported_tickers(
    payload: bytes, wanted: set[str]
) -> dict[str, dict]:
    found: dict[str, dict] = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        csv_name = next(
            (name for name in archive.namelist() if name.endswith(".csv")),
            None,
        )
        if csv_name is None:
            return {}
        with archive.open(csv_name) as raw_file:
            reader = csv.DictReader(io.TextIOWrapper(raw_file, encoding="utf-8"))
            for row in reader:
                ticker = str(row.get("ticker") or "").strip().upper()
                if ticker not in wanted:
                    continue
                found[ticker] = dict(row)
                if len(found) == len(wanted):
                    break
    return found


def _first_metadata_text(payload: dict | None, *keys: str) -> str | None:
    if not payload:
        return None
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _asset_class_from_tiingo(asset_type: object) -> str:
    normalized = str(asset_type or "").strip().lower()
    if normalized == "etf":
        return "etf"
    if normalized == "stock":
        return "equity"
    if normalized == "mutual fund":
        return "other"
    return "other"


def _compact_tiingo_metadata(payload: dict | None) -> dict:
    if not payload:
        return {}
    keys = [
        "ticker",
        "exchange",
        "assetType",
        "priceCurrency",
        "startDate",
        "endDate",
    ]
    return {key: payload[key] for key in keys if payload.get(key)}


async def _ensure_board_instruments(
    session: AsyncSession,
    board_rows: list[MarketBoardRow],
) -> dict[str, Instrument]:
    tickers = [row.ticker for row in board_rows]
    if not tickers:
        return {}
    existing = {
        instrument.ticker: instrument
        for instrument in await session.scalars(
            select(Instrument).where(Instrument.ticker.in_(tickers))
        )
    }
    for row in board_rows:
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
