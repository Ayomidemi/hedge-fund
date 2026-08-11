"""Persist and load FX rates."""

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import FxRate
from app.services.market_data.fx_provider import LiveFxRate, fetch_usd_ngn_rate

logger = logging.getLogger(__name__)


@dataclass
class FxRefreshResult:
    updated: bool = False
    rate: LiveFxRate | None = None


async def refresh_fx_rates(session: AsyncSession) -> FxRefreshResult:
    """Fetch and upsert configured FX pairs. Runs on the same schedule as
    price refresh (HF_PRICE_REFRESH_INTERVAL_SECONDS)."""
    live_rate = await fetch_usd_ngn_rate()
    if live_rate is None:
        return FxRefreshResult(updated=False)

    row = await session.scalar(
        select(FxRate).where(
            FxRate.base_currency == live_rate.base_currency,
            FxRate.quote_currency == live_rate.quote_currency,
        )
    )
    if row is None:
        row = FxRate(
            base_currency=live_rate.base_currency,
            quote_currency=live_rate.quote_currency,
            rate=live_rate.rate,
            source=live_rate.source,
            as_of=live_rate.as_of,
        )
        session.add(row)
    else:
        row.rate = live_rate.rate
        row.source = live_rate.source
        row.as_of = live_rate.as_of
        row.is_stale = False
        row.raw_payload = live_rate.raw_payload or {}

    await session.flush()
    logger.info(
        "fx_rate_refreshed",
        extra={
            "pair": f"{live_rate.base_currency}/{live_rate.quote_currency}",
            "rate": str(live_rate.rate),
            "source": live_rate.source,
        },
    )
    return FxRefreshResult(updated=True, rate=live_rate)


async def load_fx_rates(session: AsyncSession) -> dict[tuple[str, str], FxRate]:
    rows = list(await session.scalars(select(FxRate).where(FxRate.is_stale.is_(False))))
    return {(row.base_currency, row.quote_currency): row for row in rows}
