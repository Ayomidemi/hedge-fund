"""Scheduled market radar scan. Closed jurisdictions make zero vendor calls."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import engine_options
from app.services.market_radar.runner import RadarScanInProgress, run_locked_radar_scan
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="radar.scan")
def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    session_factory = async_sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            try:
                await run_locked_radar_scan(session)
            except RadarScanInProgress:
                logger.info("radar_scan_skipped_overlap")
    finally:
        await engine.dispose()
