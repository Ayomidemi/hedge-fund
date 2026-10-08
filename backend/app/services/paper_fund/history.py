"""Prepare adjusted history on the data worker, outside execution/account locks."""
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from types import SimpleNamespace
from sqlalchemy import select, func, or_
from app.core.config import settings
from app.models import Instrument, MarketPriceBar, Position, RadarRun, RadarSnapshot
from app.services.market_radar.watchlist_book import _fill_tiingo_daily

logger = logging.getLogger(__name__)


async def refresh_risk_history(session, *, now=None):
    if not settings.hf_tiingo_api_key:
        return 0
    now = now or datetime.now(timezone.utc)
    latest = select(RadarRun.id).where(RadarRun.status == "completed", RadarRun.started_at <= now).order_by(RadarRun.started_at.desc(), RadarRun.created_at.desc(), RadarRun.id.desc()).limit(1).scalar_subquery()
    radar = select(RadarSnapshot.ticker).where(RadarSnapshot.run_id == latest, RadarSnapshot.radar_priority.in_(["P0", "P1"]))
    held = select(Position.instrument_id).where(Position.quantity > 0)
    instruments = list(await session.scalars(select(Instrument).where(
        Instrument.currency == "USD", Instrument.asset_class.in_(["equity", "etf"]),
        or_(Instrument.ticker.in_(radar), Instrument.id.in_(held)))))
    if not instruments:
        return 0
    coverage = {row[0]: (row[1], row[2]) for row in (await session.execute(select(
            MarketPriceBar.instrument_id, func.count(func.distinct(MarketPriceBar.bar_date)), func.max(MarketPriceBar.bar_date)).where(
            MarketPriceBar.instrument_id.in_([i.id for i in instruments]), MarketPriceBar.source.in_(["yahoo", "tiingo"]),
            MarketPriceBar.adjusted_close_price > 0, MarketPriceBar.bar_date < now.date(),
            MarketPriceBar.bar_date >= now.date() - timedelta(days=550)).group_by(MarketPriceBar.instrument_id))).all()}
    needed = [i for i in sorted(instruments, key=lambda i: i.ticker) if
              coverage.get(i.id, (0, None))[0] < 253 or coverage[i.id][1] < now.date() - timedelta(days=3)]
    if not needed:
        return 0
    # Rotate a bounded batch, so thin IPO history cannot starve other names or
    # monopolize the data worker. The execution worker never waits for this job.
    offset = (int(now.timestamp()) // 300 * 4) % len(needed)
    # Rollback expires ORM objects, even with expire_on_commit=False. Snapshot
    # every selected instrument before an earlier request can time out.
    selected = [SimpleNamespace(id=i.id, ticker=i.ticker, currency=i.currency)
                for i in (needed[offset:] + needed[:offset])[:4]]
    refreshed = 0
    for instrument in selected:
        try:
            refreshed += await asyncio.wait_for(_fill_tiingo_daily(session, instrument, now.date() - timedelta(days=550)), timeout=12)
        except (TimeoutError, ValueError, TypeError, ArithmeticError) as error:
            await session.rollback()
            logger.warning("capital_history_refresh_failed ticker=%s error_type=%s", instrument.ticker, type(error).__name__)
    return refreshed
