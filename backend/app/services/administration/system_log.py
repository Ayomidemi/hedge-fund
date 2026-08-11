import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser
from app.models import SystemLogEntry

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
    return entry


async def list_system_logs(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 100,
    category: str | None = None,
) -> list[SystemLogEntry]:
    statement = (
        select(SystemLogEntry)
        .where(SystemLogEntry.owner_user_id == user.id)
        .order_by(SystemLogEntry.created_at.desc())
        .limit(limit)
    )
    if category and category != "all":
        statement = statement.where(SystemLogEntry.category == category)

    return list(await session.scalars(statement))


def system_log_timestamp() -> datetime:
    return datetime.now(timezone.utc)
