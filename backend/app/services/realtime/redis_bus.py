"""Redis pub/sub bridge between Celery workers and the API process.

Workers publish events after each price refresh cycle; the FastAPI process
subscribes in a lifespan task and fans events out to WebSocket clients.
Publishing is best-effort: if Redis is down the platform keeps working, it
just isn't live until Redis returns.
"""

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

try:
    import redis.asyncio as aioredis
except ModuleNotFoundError:  # pragma: no cover - depends on local install
    aioredis = None

from app.core.config import settings
from app.core.market_constants import PLATFORM_EVENTS_CHANNEL

logger = logging.getLogger(__name__)


async def publish_event(event: dict[str, Any]) -> bool:
    if aioredis is None:
        logger.warning(
            "event_publish_skipped",
            extra={
                "event_type": event.get("type"),
                "error": "Redis client package is not installed.",
            },
        )
        return False

    try:
        client = aioredis.from_url(settings.redis_url)
        try:
            await client.publish(PLATFORM_EVENTS_CHANNEL, json.dumps(event))
            if event.get("type") == "news.poll_completed":
                logger.info(
                    "news_event_published run_id=%s status=%s target_key=%s",
                    event.get("payload", {}).get("run_id"),
                    event.get("payload", {}).get("status"),
                    event.get("payload", {}).get("target_key"),
                )
            return True
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001 - best-effort by design
        logger.warning(
            "event_publish_failed event_type=%s error=%s",
            event.get("type"),
            exc,
        )
        return False


async def subscribe_events() -> AsyncGenerator[dict[str, Any]]:
    """Yield platform events forever. Caller handles cancellation."""
    if aioredis is None:
        raise RuntimeError("Redis client package is not installed.")

    client = aioredis.from_url(settings.redis_url)
    pubsub = client.pubsub()
    await pubsub.subscribe(PLATFORM_EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message["data"])
                if event.get("type") == "news.poll_completed":
                    logger.info(
                        "news_event_received run_id=%s status=%s target_key=%s",
                        event.get("payload", {}).get("run_id"),
                        event.get("payload", {}).get("status"),
                        event.get("payload", {}).get("target_key"),
                    )
                yield event
            except (json.JSONDecodeError, TypeError, KeyError):
                logger.warning("event_parse_failed")
    finally:
        await pubsub.unsubscribe(PLATFORM_EVENTS_CHANNEL)
        await pubsub.aclose()
        await client.aclose()
