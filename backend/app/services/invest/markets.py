from __future__ import annotations

import csv
import io
import json
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

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
from app.models import Instrument, InstrumentQuote, InvestMarketBoardItem
from app.services.invest.fixed_income import (
    fixed_income_response_db,
    search_fixed_income_products_db,
)
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
    exchange: str | None
    currency: str
    sector: str | None


_SEED_DIR = Path(__file__).with_name("seed_data")


@lru_cache(maxsize=1)
def _load_default_market_board_rules() -> tuple[MarketBoardRow, ...]:
    path = _SEED_DIR / "market_board_items.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        MarketBoardRow(
            ticker=row["ticker"],
            label=row["label"],
            name=row["name"],
            market=row["market"],
            group=row["group"],
            group_title=row["group_title"],
            group_description=row["group_description"],
            asset_class=row["asset_class"],
            exchange=row.get("exchange"),
            currency=row["currency"],
            sector=row.get("sector"),
        )
        for row in rows
    )


DEFAULT_MARKET_BOARD_RULES: tuple[MarketBoardRow, ...] = (
    _load_default_market_board_rules()
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

    now = datetime.now(timezone.utc)
    for index, rule in missing:
        session.add(
            _board_item_from_rule(
                rule,
                display_order=index * 10,
                tiingo_metadata=None,
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
