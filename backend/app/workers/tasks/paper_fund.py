"""Execute active paper runs even when no browser is open."""
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.locks import hold_job_lock
from app.db.session import engine_options
from app.models import PaperFundRun
from app.services.paper_fund.engine import cycle
from app.services.paper_fund.quotes import refresh_order_quotes
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
PAPER_FUND_LOCK_KEY = 4_100_004


@celery_app.task(name="paper_fund.refresh_risk_history")
def refresh_history():
    asyncio.run(_refresh_history())


async def _refresh_history():
    from app.services.paper_fund.history import refresh_risk_history
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        async with hold_job_lock(engine, 4_100_005) as locked:
            if locked:
                async with factory() as session:
                    await refresh_risk_history(session)
    finally:
        await engine.dispose()


@celery_app.task(name="paper_fund.cycle")
def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        async with hold_job_lock(engine, PAPER_FUND_LOCK_KEY) as locked:
            if not locked:
                return
            # Fetch outside account locks. A ten-minute market-data cadence
            # cannot support the engine's two-minute quote freshness rule.
            async with factory() as session:
                try:
                    await refresh_order_quotes(session)
                except Exception:
                    await session.rollback()
                    logger.exception("paper_fund_quote_refresh_failed")
            async with factory() as session:
                owners = list(await session.scalars(select(PaperFundRun.owner_user_id)
                                                    .where(PaperFundRun.status != "completed")))
            for owner in owners:
                async with factory() as session:
                    try:
                        await cycle(session, owner, include_overview=False)
                    except Exception:
                        # Roll back the entire cycle; the heartbeat then exposes
                        # the fault and one user's fault cannot stop others.
                        await session.rollback()
                        logger.exception("paper_fund_cycle_failed owner=%s", owner)
    finally:
        await engine.dispose()
