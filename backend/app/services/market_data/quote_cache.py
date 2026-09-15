"""Read helpers for the instrument_quotes cache."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, InstrumentQuote, Portfolio
from app.services.market_data.fx_convert import mark_price_for_position
from app.services.market_data.fx_refresh import load_fx_rates
from app.services.market_data.ingestion import persist_quotes
from app.services.market_data.quote_provider import fetch_quotes


async def get_cached_quote_price(
    session: AsyncSession,
    ticker: str,
) -> Decimal | None:
    """Latest non-stale native quote price for a ticker, or None."""
    quote = await session.scalar(
        select(InstrumentQuote)
        .join(Instrument, Instrument.id == InstrumentQuote.instrument_id)
        .where(Instrument.ticker == ticker.strip().upper())
        .where(InstrumentQuote.is_stale.is_(False))
    )
    return quote.price if quote is not None else None


async def get_or_fetch_quote_price(
    session: AsyncSession,
    ticker: str,
    *,
    instrument_id: UUID | None = None,
) -> Decimal | None:
    """Return a cached mark, fetching and persisting one if the cache is empty."""
    cached = await get_cached_quote_price(session, ticker)
    if cached is not None and cached > 0:
        return cached

    symbol = ticker.strip().upper()
    fetched = await fetch_quotes([symbol])
    live = fetched.get(symbol) or next(iter(fetched.values()), None)
    if live is None or live.price <= 0:
        return None
    if instrument_id is not None:
        await persist_quotes(
            session,
            {live.ticker: [instrument_id]},
            {live.ticker: live},
            mark_missing_stale=False,
        )
        await session.flush()
    return live.price


async def get_mark_price(
    session: AsyncSession,
    *,
    instrument: Instrument,
    portfolio: Portfolio,
) -> Decimal | None:
    """Latest mark in portfolio base currency, with FX conversion for NGN."""
    quote = await session.scalar(
        select(InstrumentQuote)
        .where(InstrumentQuote.instrument_id == instrument.id)
        .where(InstrumentQuote.is_stale.is_(False))
    )
    if quote is None:
        return None
    fx_rates = await load_fx_rates(session)
    return mark_price_for_position(
        quote=quote,
        instrument=instrument,
        portfolio_base_currency=portfolio.base_currency,
        fx_rates=fx_rates,
    )


async def get_mark_prices(
    session: AsyncSession,
    *,
    instrument_ids: set[UUID],
    portfolio: Portfolio,
    instruments_by_id: dict[UUID, Instrument],
) -> dict[UUID, Decimal]:
    if not instrument_ids:
        return {}

    quotes = {
        quote.instrument_id: quote
        for quote in await session.scalars(
            select(InstrumentQuote)
            .where(InstrumentQuote.instrument_id.in_(instrument_ids))
            .where(InstrumentQuote.is_stale.is_(False))
        )
    }
    fx_rates = await load_fx_rates(session)
    marks: dict[UUID, Decimal] = {}
    for instrument_id, quote in quotes.items():
        instrument = instruments_by_id.get(instrument_id)
        if instrument is None:
            continue
        mark_price = mark_price_for_position(
            quote=quote,
            instrument=instrument,
            portfolio_base_currency=portfolio.base_currency,
            fx_rates=fx_rates,
        )
        if mark_price is not None:
            marks[instrument_id] = mark_price
    return marks
