"""Row locks and advisory locks for writes that must not overlap."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.models import Portfolio, RetailAccount

PRICE_REFRESH_LOCK_KEY = 4_100_001
RADAR_SCAN_LOCK_KEY = 4_100_002
NEWS_POLL_LOCK_KEY = 4_100_003
# Use the two-integer key space, separate from legacy bigint session locks
# which may remain on pooler connections after an old worker has exited.
JOB_LOCK_NAMESPACE = 20_261_005


async def lock_retail_account(
    session: AsyncSession, account: RetailAccount
) -> RetailAccount:
    locked = await session.scalar(
        select(RetailAccount)
        .where(RetailAccount.id == account.id)
        .with_for_update()
    )
    if locked is None:
        raise RuntimeError("Invest account was not found.")
    return locked


async def lock_portfolio(session: AsyncSession, portfolio: Portfolio, *, read: bool = False) -> Portfolio:
    locked = await session.scalar(
        select(Portfolio).where(Portfolio.id == portfolio.id).with_for_update(read=read)
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise RuntimeError("Portfolio was not found.")
    return locked


async def lock_idempotency_scope(session: AsyncSession, scope: str, key: str) -> None:
    """Serialize same-key replays that do not share a parent row lock.

    Held until the current transaction commits or rolls back.
    """
    digest = hashlib.sha256(f"{scope}:{key}".encode()).digest()
    lock_key = int.from_bytes(digest[:8], "big", signed=True)
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": lock_key},
    )


@asynccontextmanager
async def hold_job_lock(engine: AsyncEngine, key: int) -> AsyncIterator[bool]:
    """Keep a dedicated lock transaction alive while job sessions commit.

    Transaction poolers may change server connections at every commit, so a
    session advisory lock can be stranded or accidentally re-entered. This
    transaction pins its server connection and releases the lock on exit,
    including exceptions, independently of commits in the job's ORM sessions.
    """
    async with engine.begin() as connection:
        locked = await connection.scalar(
            text("SELECT pg_try_advisory_xact_lock(:namespace, :key)"),
            {"namespace": JOB_LOCK_NAMESPACE, "key": key},
        )
        yield bool(locked)
