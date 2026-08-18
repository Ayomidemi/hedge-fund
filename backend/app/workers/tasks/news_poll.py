"""Scheduled news ingestion for the News Centre."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.db.session import engine_options
from app.services.news.centre import poll_news
from app.services.realtime.events import news_poll_completed_event
from app.services.realtime.redis_bus import publish_event
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="news.poll")
def run() -> None:
    asyncio.run(_run())


async def _run() -> None:
    engine = create_async_engine(settings.sqlalchemy_database_url, **engine_options)
    session_factory = async_sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    try:
        async with session_factory() as session:
            run = await poll_news(session, trigger="scheduled")
            await publish_event(
                news_poll_completed_event(
                    run_id=str(run.id),
                    status=run.status,
                    trigger=run.trigger,
                    target_scope=run.target_scope,
                    target_key=run.target_key,
                    provider_calls=run.provider_calls,
                    items_seen=run.items_seen,
                    items_created=run.items_created,
                    items_updated=run.items_updated,
                    cache_hit=run.cache_hit,
                )
            )
    finally:
        await engine.dispose()
