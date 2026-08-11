import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.models import SystemLogEntry
from app.services.realtime.events import system_log_entry_event
from app.services.realtime.redis_bus import publish_event

logger = logging.getLogger(__name__)


async def record_system_log(
    session: AsyncSession,
    *,
    owner_user_id: str | None,
    category: str,
    event: str,
    message: str,
    level: str = "info",
    context: dict[str, Any] | None = None,
) -> SystemLogEntry:
    entry = SystemLogEntry(
        owner_user_id=owner_user_id,
        level=level,
        category=category,
        event=event,
        message=message,
        context=context or {},
    )
    session.add(entry)
    await session.flush()
    logger.info(
        "system_log_recorded",
        extra={
            "category": category,
            "event": event,
            "owner_user_id": owner_user_id,
        },
    )
    # Best-effort live push; failures never block the write.
    await publish_event(
        system_log_entry_event(
            owner_user_id=owner_user_id,
            level=level,
            category=category,
            event=event,
            message=message,
        )
    )
    return entry


def _system_log_filters(
    user: AuthenticatedUser,
    *,
    category: str | None = None,
):
    filters = [SystemLogEntry.owner_user_id == user.id]
    if category and category != "all":
        filters.append(SystemLogEntry.category == category)
    return filters


async def count_system_logs(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    category: str | None = None,
) -> int:
    statement = select(func.count()).select_from(SystemLogEntry).where(
        *_system_log_filters(user, category=category)
    )
    return int(await session.scalar(statement) or 0)


async def list_system_logs(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 25,
    offset: int = 0,
    category: str | None = None,
) -> list[SystemLogEntry]:
    statement = (
        select(SystemLogEntry)
        .where(*_system_log_filters(user, category=category))
        .order_by(SystemLogEntry.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(await session.scalars(statement))


def system_log_timestamp() -> datetime:
    return datetime.now(timezone.utc)
