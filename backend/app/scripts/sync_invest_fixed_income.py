from __future__ import annotations

import argparse
import asyncio

from app.db.session import AsyncSessionLocal, engine
from app.services.invest.fixed_income import sync_fixed_income_products_from_providers


async def _run(force: bool, limit: int | None) -> None:
    async with AsyncSessionLocal() as session:
        result = await sync_fixed_income_products_from_providers(
            session,
            force=force,
            limit=limit,
        )
        await session.commit()
    await engine.dispose()
    print(
        "fixed-income sync: "
        f"requested={result.requested_count} "
        f"matched={result.matched_count} "
        f"upserted={result.upserted_count} "
        f"quotes={result.quote_count} "
        f"skipped={result.skipped_reason or 'none'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync provider-backed Invest fixed-income products."
    )
    parser.add_argument("--force", action="store_true", help="Ignore the sync TTL.")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum rows to fetch per configured provider source.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.force, args.limit))


if __name__ == "__main__":
    main()
