"""Transaction-local metadata memoization; never caches account balances."""
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession


def transaction_read_cache(session: AsyncSession) -> dict:
    if not isinstance(getattr(session, "info", None), dict):
        return {}
    transaction = session.sync_session.get_nested_transaction() or session.sync_session.get_transaction()
    previous = session.info.get("_read_metadata")
    if previous is None or previous[0] is not transaction:
        previous = (transaction, {})
        session.info["_read_metadata"] = previous
    return previous[1]


async def table_exists(session: AsyncSession, name: str) -> bool:
    key = ("table_exists", name)
    cached = transaction_read_cache(session)
    if key in cached:
        return cached[key]
    connection = await session.connection()
    exists = await connection.run_sync(lambda sync: inspect(sync).has_table(name))
    # connection() can start a transaction, so retrieve the cache again.
    transaction_read_cache(session)[key] = exists
    return exists
