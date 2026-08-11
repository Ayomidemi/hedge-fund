"""The price refresh pipeline, run by Celery beat every
HF_PRICE_REFRESH_INTERVAL_SECONDS.

Steps:
1. Build the price universe (positions + opportunities + recommendations
   + benchmarks).
2. Batch-fetch quotes through the provider chain and persist them.
3. Mark every open position to market and recompute portfolio NAV inputs.
4. Record an audit row + system log entry.
5. Publish events to Redis so the API pushes updates to connected clients.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.market_constants import PRICE_MARKET_HOURS_ONLY
from app.db.session import engine_options
from app.models import PriceRefreshRun
from app.services.administration.system_log import record_system_log
from app.services.market_data.fx_refresh import FxRefreshResult, refresh_fx_rates
from app.services.market_data.ingestion import (
    IngestionResult,
    ingest_quotes,
    is_us_market_open,
)
from app.services.market_data.mark_to_market import MarkResult, mark_open_positions
from app.services.market_data.universe import build_price_universe
from app.services.realtime.events import (
    fx_rate_updated_event,
    portfolio_marked_event,
    price_refresh_completed_event,
    quote_batch_updated_event,
)
from app.services.realtime.redis_bus import publish_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="price_refresh.run")
def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    # A fresh engine per run: asyncio.run creates a new event loop each time,
    # and pooled asyncpg connections cannot cross loops.
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    session_factory = async_sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            await _refresh_cycle(session)
    finally:
        await engine.dispose()


async def _refresh_cycle(session: AsyncSession) -> None:
    started_at = datetime.now(timezone.utc)

    # FX rates are needed around the clock for NGN → USD conversion, even when
    # US equity quotes are skipped outside regular hours.
    fx_result = await refresh_fx_rates(session)

    if PRICE_MARKET_HOURS_ONLY and not is_us_market_open(started_at):
        await session.commit()
        if fx_result.rate is not None:
            await publish_event(
                fx_rate_updated_event(
                    base_currency=fx_result.rate.base_currency,
                    quote_currency=fx_result.rate.quote_currency,
                    rate=str(fx_result.rate.rate),
                    source=fx_result.rate.source,
                    as_of=fx_result.rate.as_of.isoformat(),
                )
            )
        logger.info("price_refresh_skipped_market_closed")
        return

    run_row = PriceRefreshRun(
        started_at=started_at,
        status="running",
        interval_seconds=settings.price_refresh_interval_seconds,
    )
    session.add(run_row)
    await session.flush()

    try:
        universe = await build_price_universe(session)
        ingestion = await ingest_quotes(session, universe)
        mark_result = await mark_open_positions(session)
    except Exception as exc:
        run_row.status = "failed"
        run_row.finished_at = datetime.now(timezone.utc)
        run_row.errors = [{"error": str(exc)}]
        await session.commit()
        logger.exception("price_refresh_failed")
        raise

    run_row.status = "completed"
    run_row.finished_at = datetime.now(timezone.utc)
    run_row.ticker_count = ingestion.ticker_count
    run_row.success_count = ingestion.success_count
    run_row.failure_count = len(ingestion.failed_tickers)
    run_row.positions_marked = mark_result.positions_marked
    run_row.errors = [
        {"ticker": ticker, "error": "no quote from any provider"}
        for ticker in ingestion.failed_tickers
    ]

    await record_system_log(
        session,
        owner_user_id=None,
        category="market_data",
        event="price_refresh_completed",
        level="warning" if ingestion.failed_tickers else "info",
        message=(
            f"Refreshed {ingestion.success_count}/{ingestion.ticker_count} quotes, "
            f"marked {mark_result.positions_marked} positions."
        ),
        context={
            "run_id": str(run_row.id),
            "failed_tickers": ingestion.failed_tickers,
            "interval_seconds": settings.price_refresh_interval_seconds,
        },
    )
    await session.commit()

    await _publish_events(run_row, ingestion, mark_result, fx_result)


async def _publish_events(
    run_row: PriceRefreshRun,
    ingestion: IngestionResult,
    mark_result: MarkResult,
    fx_result: FxRefreshResult,
) -> None:
    as_of = datetime.now(timezone.utc).isoformat()

    if fx_result.rate is not None:
        await publish_event(
            fx_rate_updated_event(
                base_currency=fx_result.rate.base_currency,
                quote_currency=fx_result.rate.quote_currency,
                rate=str(fx_result.rate.rate),
                source=fx_result.rate.source,
                as_of=fx_result.rate.as_of.isoformat(),
            )
        )

    if ingestion.quotes:
        await publish_event(
            quote_batch_updated_event(
                quotes=[
                    {
                        "ticker": quote.ticker,
                        "price": str(quote.price),
                        "change_pct": (
                            str(quote.change_pct)
                            if quote.change_pct is not None
                            else None
                        ),
                        "currency": quote.currency,
                        "source": quote.source,
                        "as_of": quote.as_of.isoformat(),
                    }
                    for quote in ingestion.quotes.values()
                ],
                as_of=as_of,
            )
        )

    for portfolio in mark_result.portfolios:
        await publish_event(
            portfolio_marked_event(
                owner_user_id=portfolio.owner_user_id,
                portfolio_id=str(portfolio.portfolio_id),
                nav=str(portfolio.nav),
                cash_balance=str(portfolio.cash_balance),
                invested_value=str(portfolio.invested_value),
                position_count=portfolio.position_count,
            )
        )

    await publish_event(
        price_refresh_completed_event(
            run_id=str(run_row.id),
            ticker_count=run_row.ticker_count,
            success_count=run_row.success_count,
            failure_count=run_row.failure_count,
            positions_marked=run_row.positions_marked,
            status=run_row.status,
        )
    )
