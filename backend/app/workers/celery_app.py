"""Celery application and beat schedule.

The price refresh cadence is the only env-driven timing knob:
HF_PRICE_REFRESH_INTERVAL_SECONDS (300 on free API tiers, 10 for
penny-stock testing).

Run locally:
    celery -A app.workers.celery_app worker --beat -l info
"""

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "hedge_fund",
    broker=settings.redis_url,
    include=["app.workers.tasks.price_refresh"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    # A refresh cycle should never outlive the next tick by much.
    task_time_limit=max(settings.price_refresh_interval_seconds * 2, 120),
)

celery_app.conf.beat_schedule = {
    "price-refresh": {
        "task": "price_refresh.run",
        "schedule": float(settings.price_refresh_interval_seconds),
    },
}
