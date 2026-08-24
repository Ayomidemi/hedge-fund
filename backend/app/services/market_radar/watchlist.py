"""Always-watched names: holdings, open opportunities, sector ETFs.

These are included in the radar without extra catalog API calls.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.market_constants import RADAR_SECTOR_ETFS
from app.models import Instrument, Opportunity, Position, RadarWatchlistItem
from app.services.market_data.sessions import jurisdiction_for_ticker
from app.services.market_data.universe import quote_symbol_for
from app.services.market_radar.scoring import RadarCandidate

_CLOSED_OPPORTUNITY_STATUSES = ("closed", "rejected", "expired", "executed", "exited", "post_mortem")


@dataclass
class AlwaysWatchedSet:
    candidates: dict[str, RadarCandidate]


async def load_always_watched(session: AsyncSession) -> AlwaysWatchedSet:
    candidates: dict[str, RadarCandidate] = {}

    for ticker, sector, asset_class in RADAR_SECTOR_ETFS:
        candidates[ticker] = RadarCandidate(
            ticker=ticker,
            name=ticker,
            jurisdiction="US",
            sector=sector,
            industry=asset_class,
            asset_class="etf",
            exchange="US",
            currency="USD",
            source="seed",
            always_watched=True,
        )

    position_ids = set(
        await session.scalars(
            select(Position.instrument_id)
            .where(Position.quantity > 0)
            .where(Position.closed_at.is_(None))
            .distinct()
        )
    )
    opportunity_ids = set(
        await session.scalars(
            select(Opportunity.instrument_id)
            .where(Opportunity.status.notin_(_CLOSED_OPPORTUNITY_STATUSES))
            .where(Opportunity.closed_at.is_(None))
            .distinct()
        )
    )
    instrument_ids = position_ids | opportunity_ids

    if instrument_ids:
        instruments = {
            instrument.id: instrument
            for instrument in await session.scalars(
                select(Instrument).where(Instrument.id.in_(instrument_ids))
            )
        }
        for instrument_id, instrument in instruments.items():
            ticker = quote_symbol_for(instrument)
            jurisdiction = jurisdiction_for_ticker(ticker)
            existing = candidates.get(ticker)
            in_portfolio = instrument_id in position_ids
            in_queue = instrument_id in opportunity_ids
            if existing is None:
                candidates[ticker] = RadarCandidate(
                    ticker=ticker,
                    name=instrument.name,
                    jurisdiction=jurisdiction,
                    sector=instrument.sector,
                    industry=instrument.industry,
                    asset_class=instrument.asset_class,
                    exchange=instrument.exchange,
                    currency=instrument.currency,
                    source="book" if in_portfolio else "queue",
                    always_watched=True,
                    in_portfolio=in_portfolio,
                    in_opportunity_queue=in_queue,
                )
                continue
            existing.always_watched = True
            existing.in_portfolio = existing.in_portfolio or in_portfolio
            existing.in_opportunity_queue = existing.in_opportunity_queue or in_queue
            if in_portfolio:
                existing.source = "book"
            existing.sector = existing.sector or instrument.sector
            existing.industry = existing.industry or instrument.industry
            existing.name = instrument.name or existing.name

    watch_rows = await session.scalars(select(RadarWatchlistItem))
    for item in watch_rows:
        ticker = item.ticker.upper()
        existing = candidates.get(ticker)
        if existing is not None:
            existing.on_watchlist = True
            existing.always_watched = True
            continue
        candidates[ticker] = RadarCandidate(
            ticker=ticker,
            name=item.name,
            jurisdiction=item.jurisdiction,
            source="watchlist",
            always_watched=True,
            on_watchlist=True,
        )

    return AlwaysWatchedSet(candidates=candidates)
