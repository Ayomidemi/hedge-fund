import json
import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.api.schemas.paper_fund import PaperStart
from app.models import Base, CashLedgerEntry, Instrument, PaperFundRun, Portfolio, Position, Trade
from app.services.paper_fund.engine import start_run
from app.services.portfolio.reset import CapitalResetError, reset_capital


@skipUnless(os.environ.get("HF_TEST_DATABASE_URL"), "Requires disposable PostgreSQL database")
class CapitalResetTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = "hf_reset_" + uuid4().hex
        self.engine = create_async_engine(os.environ["HF_TEST_DATABASE_URL"], connect_args={"server_settings": {"search_path": self.schema}})
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.temp = tempfile.TemporaryDirectory()
        async with self.engine.begin() as connection:
            await connection.execute(CreateSchema(self.schema))
            await connection.run_sync(Base.metadata.create_all)
        async with self.factory() as session:
            instrument = Instrument(ticker="RESET", name="Reset test", asset_class="equity", currency="USD")
            a = Portfolio(owner_user_id="reset-owner", name="Reset", base_currency="USD", initial_capital=1000)
            b = Portfolio(owner_user_id="other-owner", name="Untouched", base_currency="USD", initial_capital=2000)
            session.add_all([instrument, a, b])
            await session.flush()
            self.portfolio_id = a.id
            self.other_id = b.id
            now = datetime.now(timezone.utc)
            for portfolio, cash in ((a, 900), (b, 1900)):
                session.add_all([
                    CashLedgerEntry(portfolio_id=portfolio.id, entry_date=now.date(), amount=cash, currency="USD", entry_type="initial_capital"),
                    Trade(portfolio_id=portfolio.id, instrument_id=instrument.id, trade_date=now, side="buy", status="filled", quantity=1, executed_price=100, fees=0, rationale="test"),
                    Position(portfolio_id=portfolio.id, instrument_id=instrument.id, quantity=1, average_cost=100, market_value=100, unrealized_pnl=0, opened_at=now),
                ])
            await session.commit()
            await start_run(session, "reset-owner", PaperStart())
            await start_run(session, "other-owner", PaperStart())

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(DropSchema(self.schema, cascade=True))
        await self.engine.dispose()
        self.temp.cleanup()

    async def test_reset_is_owner_scoped_and_creates_exact_opening_balance(self):
        backup = Path(self.temp.name) / "backup.json"
        async with self.factory() as session:
            async with session.begin():
                result = await reset_capital(session, "reset-owner", expected_portfolio_id=self.portfolio_id, backup_path=backup)
            self.assertTrue(result.executed)
            self.assertEqual((backup.stat().st_mode & 0o777), 0o600)
            saved = json.loads(backup.read_text())
            self.assertEqual(len(saved["tables"]["trades"]), 1)
            self.assertEqual(saved["portfolio"]["initial_capital"], "1000.0000")
            cash = list(await session.scalars(select(CashLedgerEntry).where(CashLedgerEntry.portfolio_id == self.portfolio_id)))
            self.assertEqual(len(cash), 1)
            self.assertEqual(cash[0].amount, Decimal("10000"))
            self.assertEqual((await session.get(Portfolio, self.portfolio_id)).initial_capital, Decimal("10000"))
            for model in (Trade, Position):
                self.assertEqual(await session.scalar(select(func.count()).select_from(model).where(model.portfolio_id == self.portfolio_id)), 0)
                self.assertEqual(await session.scalar(select(func.count()).select_from(model).where(model.portfolio_id == self.other_id)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaperFundRun).where(PaperFundRun.owner_user_id == "reset-owner")), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaperFundRun).where(PaperFundRun.owner_user_id == "other-owner")), 1)

    async def test_wrong_portfolio_or_backup_failure_cannot_delete_data(self):
        backup = Path(self.temp.name) / "backup.json"
        async with self.factory() as session:
            with self.assertRaises(CapitalResetError):
                async with session.begin():
                    await reset_capital(session, "reset-owner", expected_portfolio_id=self.other_id, backup_path=backup)
            backup.write_text("existing backup")
            with self.assertRaises(FileExistsError):
                async with session.begin():
                    await reset_capital(session, "reset-owner", expected_portfolio_id=self.portfolio_id, backup_path=backup)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Trade).where(Trade.portfolio_id == self.portfolio_id)), 1)
