"""Prepare history for supported discoveries before ranking, off execution locks."""
import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from time import perf_counter

from sqlalchemy import case, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.models import (
    Instrument, MarketPriceBar, Position, RadarHistoryPreparation, RadarRun,
    RadarSnapshot, RadarUniverseMember,
)
from app.services.market_radar.watchlist_book import _fill_tiingo_daily
from app.services.paper_fund.calendar import session_bounds

logger = logging.getLogger(__name__)
BATCH_SIZE = 4
LOOKBACK_DAYS = 550
DISCOVERY_RETENTION_DAYS = 14
REQUIRED_BARS = 253


def _supported(item):
    return (item.currency == "USD" and item.asset_class in {"equity", "etf"}
            and not item.ticker.upper().endswith(".NG"))


def _previous_session(now):
    # Match radar's completed-date rule, including weekends and exchange holidays.
    for offset in range(1, 11):
        day = now.date() - timedelta(days=offset)
        if session_bounds(datetime.combine(day, time(16), timezone.utc)):
            return day
    return None


async def _eligible(session, now):
    def identity_columns(model):
        return tuple(getattr(model, name) for name in (
            "ticker", "name", "currency", "asset_class", "exchange", "sector", "industry"))

    catalog = (await session.execute(select(*identity_columns(RadarUniverseMember)).where(
        RadarUniverseMember.is_active.is_(True), RadarUniverseMember.jurisdiction == "US")))
    # Retain discoveries across scans so one disappearance from a mover list
    # cannot remove their turn. Ignore failed/future scans and carried observations.
    # Do not sort/transfer entire evidence JSON and sparklines for two weeks
    # of snapshots when selection only needs identity metadata.
    discoveries = (await session.execute(select(*identity_columns(RadarSnapshot)).join(RadarRun).where(
        RadarRun.status == "completed", RadarRun.started_at <= now,
        RadarRun.started_at >= now - timedelta(days=DISCOVERY_RETENTION_DAYS),
        RadarSnapshot.jurisdiction == "US", RadarSnapshot.carried_forward.is_(False),
    ).distinct(RadarSnapshot.ticker).order_by(
        RadarSnapshot.ticker, RadarRun.started_at.desc(), RadarRun.created_at.desc(), RadarRun.id.desc())))
    held = list(await session.scalars(select(Instrument).where(
        Instrument.id.in_(select(Position.instrument_id).where(Position.quantity > 0)))))
    # Existing instrument metadata takes precedence over discovery heuristics.
    items = {item.ticker: item for item in [*discoveries, *catalog, *held]}
    known = {item.ticker: item for item in await session.scalars(
        select(Instrument).where(Instrument.ticker.in_(items)))} if items else {}
    result = {}
    for ticker, item in items.items():
        identity = known.get(ticker, item)
        if _supported(identity):
            result[ticker] = SimpleNamespace(
                id=getattr(known.get(ticker), "id", None), ticker=ticker,
                name=identity.name, currency=identity.currency, asset_class=identity.asset_class,
                exchange=identity.exchange, sector=identity.sector, industry=identity.industry,
            )
    return result, {item.ticker for item in held if _supported(item)}


async def _coverage(session, ids, now):
    if not ids:
        return {}
    # Match radar's provider precedence before validating fields; a duplicate
    # provider row cannot make a broken preferred observation look complete.
    preferred = select(
        MarketPriceBar.instrument_id, MarketPriceBar.bar_date,
        MarketPriceBar.adjusted_close_price, MarketPriceBar.close_price, MarketPriceBar.volume,
    ).where(
        MarketPriceBar.instrument_id.in_(ids), MarketPriceBar.source.in_(["tiingo", "yahoo"]),
        MarketPriceBar.bar_date < now.date(),
        MarketPriceBar.bar_date >= now.date() - timedelta(days=LOOKBACK_DAYS),
    ).distinct(MarketPriceBar.instrument_id, MarketPriceBar.bar_date).order_by(
        MarketPriceBar.instrument_id, MarketPriceBar.bar_date,
        case((MarketPriceBar.source == "tiingo", 0), else_=1),
    ).subquery()
    bars = preferred.c
    rows = (await session.execute(select(
        bars.instrument_id, func.count(func.distinct(bars.bar_date)), func.max(bars.bar_date),
        func.count(func.distinct(bars.bar_date)).filter(bars.volume >= 0),
    ).where(
        bars.adjusted_close_price > 0, bars.adjusted_close_price < float("inf"),
        bars.close_price > 0, bars.close_price < float("inf"),
        bars.bar_date < now.date(), bars.bar_date >= now.date() - timedelta(days=LOOKBACK_DAYS),
    ).group_by(bars.instrument_id))).all()
    return {row[0]: (row[1], row[2], row[3]) for row in rows}


def _ready(coverage, expected):
    count, last, volumes = coverage
    return expected is not None and count >= REQUIRED_BARS and last >= expected and volumes >= 20


def _select_batch(rows, held):
    # Reserve one holding slot and the rest for discoveries when available.
    # Within each lane, persisted oldest-attempt order survives changing lists.
    ordered = sorted(rows, key=lambda row: (
        row.last_attempt_at or datetime.min.replace(tzinfo=timezone.utc), row.ticker))
    urgent = next((row for row in ordered if row.ticker in held), None)
    remaining = [row for row in ordered if row.ticker not in held]
    remaining += [row for row in ordered if row.ticker in held and row is not urgent]
    return ([urgent] if urgent else []) + remaining[:BATCH_SIZE - bool(urgent)]


async def refresh_risk_history(session, *, now=None):
    if not settings.hf_tiingo_api_key:
        return 0
    started = perf_counter()
    now = now or datetime.now(timezone.utc)
    expected = _previous_session(now)
    if expected is None:
        return 0
    eligible, held = await _eligible(session, now)
    if not eligible:
        return 0
    await session.execute(insert(RadarHistoryPreparation).values([
        dict(ticker=ticker, last_seen_at=now, next_attempt_at=now,
             status="pending", failure_count=0, bar_count=0)
        for ticker in eligible
    ]).on_conflict_do_update(
        index_elements=["ticker"], set_={"last_seen_at": now},
        where=RadarHistoryPreparation.last_seen_at < now - timedelta(hours=1),
    ))
    rows = list(await session.scalars(select(RadarHistoryPreparation).where(
        RadarHistoryPreparation.ticker.in_(eligible), RadarHistoryPreparation.next_attempt_at <= now)))
    # Ready/backing-off names do not need their full history aggregated again.
    coverage = await _coverage(session, [eligible[row.ticker].id for row in rows
                                         if eligible[row.ticker].id], now)
    needed = []
    for row in rows:
        observed = coverage.get(eligible[row.ticker].id, (0, None, 0))
        row.bar_count, row.last_bar_date = observed[:2]
        if _ready(observed, expected):
            row.status, row.failure_count, row.last_error = "ready", 0, None
            row.next_attempt_at = now + timedelta(hours=6)
        else:
            needed.append(row)
    selected = _select_batch(needed, held)
    # Persist attempts before network I/O. A crashed worker gets a bounded lease,
    # and rollback for one ticker cannot undo progress for other tickers.
    selected_tickers = [row.ticker for row in selected]
    for row in selected:
        row.last_attempt_at, row.next_attempt_at, row.status = now, now + timedelta(minutes=15), "preparing"
    await session.commit()
    selection_seconds = perf_counter() - started
    refreshed = 0
    for ticker in selected_tickers:
        instrument = eligible[ticker]
        error_type = None
        saved = 0
        try:
            if instrument.id is None:
                await session.execute(insert(Instrument).values(
                    ticker=ticker, name=instrument.name[:255], currency=instrument.currency,
                    asset_class=instrument.asset_class, exchange=instrument.exchange,
                    sector=instrument.sector, industry=instrument.industry,
                ).on_conflict_do_nothing(index_elements=["ticker"]))
                existing = await session.scalar(select(Instrument).where(Instrument.ticker == ticker))
                if not _supported(existing):
                    raise ValueError("Instrument is no longer supported")
                instrument.id = existing.id
                await session.commit()
            saved = await asyncio.wait_for(_fill_tiingo_daily(
                session, instrument, now.date() - timedelta(days=LOOKBACK_DAYS),
                end=now.date() - timedelta(days=1)), timeout=12)
        except (TimeoutError, ValueError, TypeError, ArithmeticError, SQLAlchemyError) as error:
            await session.rollback()
            error_type = type(error).__name__
            logger.warning("capital_history_refresh_failed ticker=%s error_type=%s", ticker, error_type)
        refreshed += saved
        observed = (await _coverage(session, [instrument.id], now)).get(instrument.id, (0, None, 0))
        row = await session.get(RadarHistoryPreparation, ticker)
        row.bar_count, row.last_bar_date = observed[:2]
        if _ready(observed, expected):
            row.status, row.failure_count, row.last_error = "ready", 0, None
            row.next_attempt_at = now + timedelta(hours=6)
        elif error_type or not saved:
            row.failure_count += 1
            row.status, row.last_error = "retry", error_type or "NoUsableHistory"
            row.next_attempt_at = now + timedelta(minutes=min(30 * 2 ** min(row.failure_count - 1, 6), 1440))
        else:
            # IPOs/short histories can already support radar but not full risk
            # calibration. Keep the gap explicit and avoid downloading it every cycle.
            row.status, row.failure_count, row.last_error = "partial", 0, None
            row.next_attempt_at = now + timedelta(hours=12)
        await session.commit()
    logger.info("radar_history_prepared eligible=%s due=%s attempted=%s bars_saved=%s selection_seconds=%.3f total_seconds=%.3f",
                len(eligible), len(rows), len(selected_tickers), refreshed,
                selection_seconds, perf_counter() - started)
    return refreshed
