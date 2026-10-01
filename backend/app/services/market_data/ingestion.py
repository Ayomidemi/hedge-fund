"""Quote ingestion: fetch live prices and persist them.

Writes to:
- instrument_quotes  (latest mark per instrument, single source of truth)
- market_price_bars  (today's bar, source="live", keeps risk/ML history warm)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.market_constants import PRICE_STALE_AFTER_SECONDS
from app.models import InstrumentQuote, MarketPriceBar
from app.services.market_data.quote_provider import LiveQuote, fetch_quotes
from app.services.market_data.sessions import is_us_market_open

logger = logging.getLogger(__name__)

LIVE_BAR_SOURCE = "live"


@dataclass
class IngestionResult:
    ticker_count: int = 0
    success_count: int = 0
    failed_tickers: list[str] = field(default_factory=list)
    quotes: dict[str, LiveQuote] = field(default_factory=dict)


__all__ = [
    "IngestionResult",
    "LIVE_BAR_SOURCE",
    "ingest_quotes",
    "is_us_market_open",
    "persist_quotes",
]


async def ingest_quotes(
    session: AsyncSession,
    universe: dict[str, list[uuid.UUID]],
) -> IngestionResult:
    result = IngestionResult(ticker_count=len(universe))
    if not universe:
        return result

    fetched = await fetch_quotes(sorted(universe))
    result.quotes = fetched
    result.success_count = len(fetched)
    result.failed_tickers = sorted(set(universe) - set(fetched))
    await persist_quotes(session, universe, fetched, mark_missing_stale=True)
    logger.info(
        "quotes_ingested",
        extra={
            "ticker_count": result.ticker_count,
            "success_count": result.success_count,
            "failed": result.failed_tickers,
        },
    )
    return result


async def persist_quotes(
    session: AsyncSession,
    universe: dict[str, list[uuid.UUID]],
    quotes: dict[str, LiveQuote],
    *,
    mark_missing_stale: bool = False,
) -> None:
    """Write already-fetched quotes into instrument_quotes and today's live bar.

    Radar uses this so a catalog tape becomes cacheable history without a
    second vendor round-trip. The live-price loop still fetches, then calls
    the same writer.
    """
    if not universe:
        return

    instrument_ids = [
        instrument_id
        for id_group in universe.values()
        for instrument_id in id_group
    ]
    existing_quotes = {
        row.instrument_id: row
        for row in await session.scalars(
            select(InstrumentQuote).where(
                InstrumentQuote.instrument_id.in_(instrument_ids)
            )
        )
    }
    today = date.today()
    existing_bars = {
        bar.instrument_id: bar
        for bar in await session.scalars(
            select(MarketPriceBar)
            .where(MarketPriceBar.instrument_id.in_(instrument_ids))
            .where(MarketPriceBar.bar_date == today)
            .where(MarketPriceBar.source == LIVE_BAR_SOURCE)
        )
    }

    stale_cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=PRICE_STALE_AFTER_SECONDS
    )
    new_quotes: list[InstrumentQuote] = []
    new_bars: list[MarketPriceBar] = []

    for ticker, id_group in universe.items():
        quote = quotes.get(ticker)
        for instrument_id in id_group:
            row = existing_quotes.get(instrument_id)

            if quote is None:
                if mark_missing_stale and row is not None and row.as_of < stale_cutoff:
                    row.is_stale = True
                continue

            if row is None:
                row = InstrumentQuote(
                    id=uuid.uuid4(),
                    instrument_id=instrument_id,
                    price=quote.price,
                    source=quote.source,
                    as_of=quote.as_of,
                    currency=quote.currency,
                    is_stale=False,
                    raw_payload=quote.raw_payload or {},
                )
                new_quotes.append(row)
                existing_quotes[instrument_id] = row
            row.price = quote.price
            row.previous_close = (
                quote.previous_close
                if quote.previous_close is not None
                else row.previous_close
            )
            row.change_pct = (
                quote.change_pct
                if quote.change_pct is not None
                else _change_pct(quote.price, row.previous_close)
            )
            row.day_open = quote.day_open if quote.day_open is not None else row.day_open
            row.day_high = quote.day_high if quote.day_high is not None else row.day_high
            row.day_low = quote.day_low if quote.day_low is not None else row.day_low
            row.volume = quote.volume if quote.volume is not None else row.volume
            row.currency = quote.currency
            row.source = quote.source
            row.as_of = quote.as_of
            row.is_stale = False
            row.raw_payload = quote.raw_payload or {}

            _upsert_live_bar(
                new_bars, existing_bars, instrument_id, today, quote
            )

    if new_quotes:
        quote_insert = pg_insert(InstrumentQuote).values(
            [
                {
                    "id": row.id,
                    "instrument_id": row.instrument_id,
                    "price": row.price,
                    "previous_close": row.previous_close,
                    "change_pct": row.change_pct,
                    "day_open": row.day_open,
                    "day_high": row.day_high,
                    "day_low": row.day_low,
                    "volume": row.volume,
                    "currency": row.currency,
                    "source": row.source,
                    "as_of": row.as_of,
                    "is_stale": row.is_stale,
                    "raw_payload": row.raw_payload or {},
                }
                for row in new_quotes
            ]
        )
        quote_insert = quote_insert.on_conflict_do_update(
            index_elements=["instrument_id"],
            set_={
                "price": quote_insert.excluded.price,
                "previous_close": func.coalesce(
                    quote_insert.excluded.previous_close,
                    InstrumentQuote.previous_close,
                ),
                "change_pct": quote_insert.excluded.change_pct,
                "day_open": func.coalesce(
                    quote_insert.excluded.day_open, InstrumentQuote.day_open
                ),
                "day_high": func.coalesce(
                    quote_insert.excluded.day_high, InstrumentQuote.day_high
                ),
                "day_low": func.coalesce(
                    quote_insert.excluded.day_low, InstrumentQuote.day_low
                ),
                "volume": func.coalesce(
                    quote_insert.excluded.volume, InstrumentQuote.volume
                ),
                "currency": quote_insert.excluded.currency,
                "source": quote_insert.excluded.source,
                "as_of": quote_insert.excluded.as_of,
                "is_stale": quote_insert.excluded.is_stale,
                "raw_payload": quote_insert.excluded.raw_payload,
                "updated_at": func.now(),
            },
        )
        await session.execute(quote_insert)

    if new_bars:
        bar_insert = pg_insert(MarketPriceBar).values(
            [
                {
                    "id": bar.id,
                    "instrument_id": bar.instrument_id,
                    "bar_date": bar.bar_date,
                    "source": bar.source,
                    "open_price": bar.open_price,
                    "high_price": bar.high_price,
                    "low_price": bar.low_price,
                    "close_price": bar.close_price,
                    "volume": bar.volume,
                    "currency": bar.currency,
                    "raw_payload": bar.raw_payload or {},
                }
                for bar in new_bars
            ]
        )
        bar_insert = bar_insert.on_conflict_do_update(
            constraint="uq_market_price_bars_instrument_date_source",
            set_={
                "close_price": bar_insert.excluded.close_price,
                "open_price": func.coalesce(
                    MarketPriceBar.open_price, bar_insert.excluded.open_price
                ),
                "high_price": func.greatest(
                    func.coalesce(
                        MarketPriceBar.high_price, bar_insert.excluded.high_price
                    ),
                    func.coalesce(
                        bar_insert.excluded.high_price, MarketPriceBar.high_price
                    ),
                ),
                "low_price": func.least(
                    func.coalesce(
                        MarketPriceBar.low_price, bar_insert.excluded.low_price
                    ),
                    func.coalesce(
                        bar_insert.excluded.low_price, MarketPriceBar.low_price
                    ),
                ),
                "volume": func.coalesce(
                    bar_insert.excluded.volume, MarketPriceBar.volume
                ),
                "currency": bar_insert.excluded.currency,
                "updated_at": func.now(),
            },
        )
        await session.execute(bar_insert)

    await session.flush()


def _upsert_live_bar(
    new_bars: list[MarketPriceBar],
    existing_bars: dict[uuid.UUID, MarketPriceBar],
    instrument_id: uuid.UUID,
    bar_date: date,
    quote: LiveQuote,
) -> None:
    bar = existing_bars.get(instrument_id)
    if bar is None:
        bar = MarketPriceBar(
            id=uuid.uuid4(),
            instrument_id=instrument_id,
            bar_date=bar_date,
            source=LIVE_BAR_SOURCE,
            close_price=quote.price,
            currency=quote.currency,
            raw_payload={},
        )
        new_bars.append(bar)
        existing_bars[instrument_id] = bar

    bar.close_price = quote.price
    bar.open_price = quote.day_open or bar.open_price or quote.price
    high_candidates = [
        value for value in (bar.high_price, quote.day_high, quote.price) if value
    ]
    low_candidates = [
        value for value in (bar.low_price, quote.day_low, quote.price) if value
    ]
    bar.high_price = max(high_candidates)
    bar.low_price = min(low_candidates)
    bar.volume = quote.volume or bar.volume
    bar.currency = quote.currency


def _change_pct(price: Decimal, previous_close: Decimal | None) -> Decimal | None:
    if previous_close is None or previous_close <= 0:
        return None
    return ((price - previous_close) / previous_close * 100).quantize(Decimal("0.0001"))
