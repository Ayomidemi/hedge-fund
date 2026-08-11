"""Read helpers for the instrument_quotes cache."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, InstrumentQuote, Portfolio
from app.services.market_data.fx_convert import mark_price_for_position
from app.services.market_data.fx_refresh import load_fx_rates


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
