"""Builds the set of instruments whose prices we keep fresh.

Universe = open positions (all portfolios) + open opportunities + recent
model recommendations + benchmark tickers. Deduplicated globally because
instruments are shared across users.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.market_constants import (
    BENCHMARK_TICKERS,
    RECOMMENDATION_UNIVERSE_DAYS,
)
from app.models import Instrument, ModelRecommendation, Opportunity, Position

logger = logging.getLogger(__name__)

_CLOSED_OPPORTUNITY_STATUSES = ("closed", "rejected", "expired", "executed")


async def build_price_universe(session: AsyncSession) -> dict[str, list[uuid.UUID]]:
    """Return a mapping of quote symbol -> instrument ids for all instruments
    that need live quotes this cycle. Multiple instruments can share one
    quote symbol (e.g. duplicate rows for the same listed security), and each
    gets its own quote row."""
    instrument_ids: set[uuid.UUID] = set()

    position_ids = await session.scalars(
        select(Position.instrument_id)
        .where(Position.quantity > 0)
        .where(Position.closed_at.is_(None))
        .distinct()
    )
    instrument_ids.update(position_ids)

    opportunity_ids = await session.scalars(
        select(Opportunity.instrument_id)
        .where(Opportunity.status.notin_(_CLOSED_OPPORTUNITY_STATUSES))
        .where(Opportunity.closed_at.is_(None))
        .distinct()
    )
    instrument_ids.update(opportunity_ids)

    recommendation_cutoff = datetime.now(timezone.utc) - timedelta(
        days=RECOMMENDATION_UNIVERSE_DAYS
    )
    recommendation_ids = await session.scalars(
        select(ModelRecommendation.instrument_id)
        .where(ModelRecommendation.generated_at >= recommendation_cutoff)
        .distinct()
    )
    instrument_ids.update(recommendation_ids)

    benchmark_instruments = await session.scalars(
        select(Instrument).where(Instrument.ticker.in_(BENCHMARK_TICKERS))
    )
    instrument_ids.update(instrument.id for instrument in benchmark_instruments)

    if not instrument_ids:
        return {}

    instruments = await session.scalars(
        select(Instrument).where(Instrument.id.in_(instrument_ids))
    )
    universe: dict[str, list[uuid.UUID]] = {}
    for instrument in instruments:
        universe.setdefault(quote_symbol_for(instrument), []).append(instrument.id)
    logger.info("price_universe_built", extra={"ticker_count": len(universe)})
    return universe


_NG_EXCHANGES = {"NG", "NGX"}


def quote_symbol_for(instrument: Instrument) -> str:
    """Provider routing key. Nigerian instruments are routed to NGN Market via
    a .NG suffix regardless of how their ticker is stored, so a ticker like
    MTN (MTN Nigeria, exchange=NG) is never confused with the US ticker MTN."""
    ticker = instrument.ticker.upper()
    if ticker.endswith(".NG"):
        return ticker
    if (instrument.exchange or "").strip().upper() in _NG_EXCHANGES:
        return f"{ticker}.NG"
    return ticker
