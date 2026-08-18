"""Celery application and beat schedule.

Price refresh and news polling use env-driven timing/scope knobs:
HF_PRICE_REFRESH_INTERVAL_SECONDS, HF_NEWS_POLL_INTERVAL_SECONDS, and
HF_NEWS_POLL_JURISDICTIONS.

Run locally:
    celery -A app.workers.celery_app worker --beat -l info
"""

from celery import Celery

from app.core.config import settings
from app.core.market_constants import RADAR_SCAN_INTERVAL_SECONDS

celery_app = Celery(
    "hedge_fund",
    broker=settings.redis_url,
    include=[
        "app.workers.tasks.price_refresh",
        "app.workers.tasks.radar_scan",
        "app.workers.tasks.news_poll",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    # A refresh cycle should never outlive the next tick by much.
    task_time_limit=max(settings.price_refresh_interval_seconds * 2, 180),
)

celery_app.conf.beat_schedule = {
    "price-refresh": {
        "task": "price_refresh.run",
        "schedule": float(settings.price_refresh_interval_seconds),
    },
    "market-radar": {
        "task": "radar.scan",
        "schedule": float(RADAR_SCAN_INTERVAL_SECONDS),
    },
    "news-poll": {
        "task": "news.poll",
        "schedule": float(settings.news_poll_interval_seconds),
    },
}
