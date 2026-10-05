"""Celery application and beat schedule.

Price refresh and news polling use env-driven timing/scope knobs:
HF_PRICE_REFRESH_INTERVAL_SECONDS, HF_NEWS_POLL_INTERVAL_SECONDS, and
HF_NEWS_POLL_JURISDICTIONS.

Run locally:
    ./scripts/dev-backend.sh
"""

from celery import Celery, current_app
from celery.app import trace
from celery.app.trace import build_tracer
from celery.signals import worker_process_init
from celery.utils.nodenames import gethostname
from kombu.serialization import prepare_accept_content

from app.core.config import settings
from app.core.market_constants import RADAR_SCAN_INTERVAL_SECONDS

celery_app = Celery(
    "hedge_fund",
    broker=settings.redis_url,
    include=[
        "app.workers.tasks.price_refresh",
        "app.workers.tasks.radar_scan",
        "app.workers.tasks.news_poll",
        "app.workers.tasks.paper_fund",
    ],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    worker_prefetch_multiplier=1,
    # Long research/data jobs must never occupy the only execution worker.
    task_routes={"paper_fund.cycle": {"queue": "execution"}},
    # A refresh cycle should never outlive the next tick by much.
    task_time_limit=max(settings.price_refresh_interval_seconds * 2, 180),
)

@worker_process_init.connect
def _prime_celery_fast_trace(**_kwargs) -> None:
    """Celery 5.6 spawn children call fast_trace_task with an empty cache.

    The pool process is a fresh interpreter, so it does not inherit the
    parent's ``trace._localized`` list. ``process_initializer`` builds
    tracers on the worker app and then leaves that list empty. Fill it
    from the current worker app. The module-level app is a different
    instance in the child and its registry does not have these tasks.
    """
    if len(trace._localized) == 3:
        return
    app = current_app._get_current_object()
    hostname = gethostname()
    for name, task in app.tasks.items():
        if getattr(task, "__trace__", None) is None:
            task.__trace__ = build_tracer(
                name, task, app.loader, hostname, app=app
            )
    trace._localized[:] = [
        app._tasks,
        prepare_accept_content(app.conf.accept_content),
        hostname,
    ]


celery_app.conf.beat_schedule = {
    "paper-fund": {"task": "paper_fund.cycle", "schedule": 30.0,
                   "options": {"expires": 30}},
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
