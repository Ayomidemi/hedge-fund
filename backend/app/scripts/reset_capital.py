"""Preview or execute an owner-scoped reset to $10,000 of paper capital."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from app.db.session import AsyncSessionLocal, engine
from app.services.portfolio.reset import preview_capital_reset, reset_capital


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-user-id", required=True, help="Exact owner of the Capital portfolio.")
    parser.add_argument("--expected-portfolio-id", type=UUID,
                        help="Required for execution; must match this owner's existing portfolio.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Read-only summary (the default).")
    mode.add_argument("--execute", action="store_true", help="Reset the owner's Capital records in one transaction.")
    parser.add_argument("--backup", type=Path,
                        help="Required for execution; new private JSON backup written before deletion.")
    return parser


async def _run(args: argparse.Namespace) -> dict:
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                if args.execute:
                    summary = await reset_capital(
                        session, args.owner_user_id,
                        expected_portfolio_id=args.expected_portfolio_id,
                        backup_path=args.backup,
                    )
                else:
                    summary = await preview_capital_reset(
                        session, args.owner_user_id,
                        expected_portfolio_id=args.expected_portfolio_id,
                    )
            # This response is emitted only after the transaction commits.
            return summary.to_dict()
    finally:
        await engine.dispose()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.execute and (args.expected_portfolio_id is None or args.backup is None):
        parser.error("--execute requires --expected-portfolio-id and --backup.")
    print(json.dumps(asyncio.run(_run(args)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
