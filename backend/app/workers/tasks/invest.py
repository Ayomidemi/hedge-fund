"""Run Invest automatic plans without blocking Capital's execution worker."""
import asyncio
import logging

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.locks import hold_job_lock
from app.db.session import engine_options
from app.models import InvestManagedOrder, RetailAccount
from app.services.invest.automation import cycle_account, refresh_managed_quotes
from app.services.paper_fund.health import track_job
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
INVEST_LOCK_KEY = 4_100_007


@celery_app.task(name="invest.cycle", time_limit=90)
def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        async with hold_job_lock(engine, INVEST_LOCK_KEY) as locked:
            if not locked:
                return
            async with track_job(factory, "invest"):
                async with asyncio.timeout(80):
                    await _execute(factory)
    finally:
        await engine.dispose()


async def _execute(factory) -> None:
    failed = False
    async with factory() as session:
        try:
            await refresh_managed_quotes(session)
        except Exception:
            await session.rollback()
            failed = True
            logger.warning("invest_quote_refresh_failed")
    async with factory() as session:
        active_plan = exists().where(
            InvestManagedOrder.account_id == RetailAccount.id,
            InvestManagedOrder.status.in_(["pending", "open"]),
        )
        account_ids = list(await session.scalars(
            select(RetailAccount.id).where(
                RetailAccount.broker_provider == "PAPER",
                RetailAccount.status == "active",
                or_(
                    RetailAccount.trading_mode == "automatic",
                    RetailAccount.automation_status == "halted",
                    active_plan,
                ),
            )
        ))
    for account_id in account_ids:
        async with factory() as session:
            try:
                await cycle_account(session, account_id)
            except Exception:
                await session.rollback()
                failed = True
                logger.warning("invest_cycle_failed", extra={"account_id": str(account_id)})
    if failed:
        raise RuntimeError("InvestCycleIncomplete")
