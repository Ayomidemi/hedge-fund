"""Run only against an explicitly supplied, migrated disposable PostgreSQL DB.

HF_TEST_DATABASE_URL=postgresql+asyncpg://... python -m unittest tests.integration.test_paper_fund_postgres -v
"""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, skipUnless
from uuid import uuid4

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.api.schemas.operating_core import CashWithdrawalCreate
from app.api.schemas.paper_fund import PaperStart
from app.core.auth import AuthenticatedUser, require_capital_user
from app.db.session import get_session
from app.main import app
from app.models import Base, CashLedgerEntry, Instrument, InstrumentQuote, MarketPriceBar, PaperFundRun, PaperOrder, Position, RadarRun, RadarSnapshot, Trade
from app.services.paper_fund.engine import control_run, cycle, overview, start_run
from app.services.portfolio.operating_core import CapitalValidationError, create_cash_withdrawal, get_or_create_default_portfolio

D = Decimal
NOW = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)
TEST_URL = os.environ.get("HF_TEST_DATABASE_URL")


@skipUnless(TEST_URL, "Set HF_TEST_DATABASE_URL to a disposable migrated PostgreSQL database.")
class PostgresPaperFundTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = f"hf_audit_{uuid4().hex}"
        self.engine = create_async_engine(TEST_URL, connect_args={"server_settings": {"search_path": self.schema}})
        async with self.engine.begin() as connection:
            await connection.execute(CreateSchema(self.schema))
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.owner = f"paper-audit-{uuid4().hex}"
        self.user = AuthenticatedUser(id=self.owner, email=None)

    async def asyncTearDown(self):
        app.dependency_overrides.clear()
        async with self.engine.begin() as connection:
            await connection.execute(DropSchema(self.schema, cascade=True))
        await self.engine.dispose()

    async def seed_signal(self):
        ticker = "TEST" + uuid4().hex[:10].upper()
        async with self.factory() as session:
            instrument = Instrument(ticker=ticker, name="Paper test", currency="USD", asset_class="equity", sector="Technology")
            run = RadarRun(started_at=NOW, finished_at=NOW, status="completed")
            session.add_all([instrument, run])
            await session.flush()
            session.add(InstrumentQuote(instrument_id=instrument.id, price=D("100"), previous_close=D("95"),
                                        currency="USD", source="fmp", as_of=NOW, is_stale=False,
                                        raw_payload={"timestamp": int(NOW.timestamp())}))
            session.add(RadarSnapshot(run_id=run.id, ticker=ticker, name="Paper test", jurisdiction="US",
                                      currency="USD", asset_class="equity", sector="Technology", source="fmp",
                                      price=D("100"), change_pct=D("5"), volume_ratio=D("3"),
                                      evidence={"avg_dollar_volume": "10000000"}, as_of=NOW, source_as_of=NOW,
                                      radar_priority="P1", priority_score=D("90")))
            await session.commit()
            return instrument.id, run.id

    async def quote(self, instrument_id, price, at):
        async with self.factory() as session:
            quote = await session.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument_id))
            quote.price = D(price)
            quote.as_of = at
            quote.raw_payload = {"timestamp": int(at.timestamp())}
            await session.commit()

    async def call_cycle(self, at=NOW):
        async with self.factory() as session:
            return await cycle(session, self.owner, now=at)

    async def test_concurrent_start_and_cycle_produce_one_order_and_one_fill(self):
        instrument_id, _ = await self.seed_signal()

        async def start():
            async with self.factory() as session:
                return await start_run(session, self.owner, PaperStart(), now=NOW, idempotency_key="one-trial")

        a, b = await asyncio.gather(start(), start())
        self.assertEqual(a.run.id, b.run.id)
        a, b = await asyncio.gather(self.call_cycle(), self.call_cycle())
        self.assertEqual(len(a.orders), 1)
        self.assertEqual(a.orders[0].status, "pending")
        self.assertEqual(a.run.cash_balance, D("10000"))
        self.assertGreater(a.run.reserved_cash, 0)
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        a, b = await asyncio.gather(self.call_cycle(at), self.call_cycle(at))
        self.assertEqual(a.orders[0].status, "open")
        self.assertEqual(a.run.cash_balance, D("9098.64"))
        self.assertEqual(b.run.cash_balance, a.run.cash_balance)
        self.assertEqual(a.run.total_pnl, a.run.realized_pnl + a.run.unrealized_pnl)
        # Target exit and cash P&L remain reconciled after another duplicate cycle.
        at += timedelta(seconds=30)
        await self.quote(instrument_id, "107", at)
        a, b = await asyncio.gather(self.call_cycle(at), self.call_cycle(at))
        self.assertEqual(a.orders[0].status, "closed")
        self.assertEqual(a.run.total_pnl, a.run.realized_pnl)
        self.assertEqual(a.run.unrealized_pnl, 0)
        self.assertEqual(a.run.cash_balance, b.run.cash_balance)
        async with self.factory() as session:
            count = await session.scalar(select(func.count(PaperOrder.id)).where(PaperOrder.run_id == a.run.id))
            self.assertEqual(count, 1)

    async def test_pause_resume_week_end_and_start_replay_preserve_history(self):
        async with self.factory() as session:
            initial = await start_run(session, self.owner, PaperStart(), now=NOW, idempotency_key="original")
        async with self.factory() as session:
            paused = await control_run(session, self.owner, "pause")
            self.assertEqual(paused.run.status, "paused")
            resumed = await control_run(session, self.owner, "resume")
            self.assertEqual(resumed.run.status, "running")
        ended = await self.call_cycle(NOW + timedelta(days=7))
        self.assertEqual(ended.run.status, "completed")
        self.assertEqual(ended.run.equity, D("10000"))
        async with self.factory() as session:
            replay = await start_run(session, self.owner, PaperStart(), now=NOW + timedelta(days=8), idempotency_key="original")
            self.assertEqual(replay.run.id, initial.run.id)
            self.assertEqual(replay.run.status, "completed")
            next_run = await start_run(session, self.owner, PaperStart(), now=NOW + timedelta(days=8), idempotency_key="next")
            self.assertNotEqual(next_run.run.id, initial.run.id)
            archive = await overview(session, self.owner, run_id=initial.run.id)
            self.assertEqual(archive.run.status, "completed")

    async def test_api_owner_isolation_and_schema_validation(self):
        async def dependency_session():
            async with self.factory() as session:
                yield session
        app.dependency_overrides[get_session] = dependency_session
        app.dependency_overrides[require_capital_user] = lambda: self.user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            bad = await client.post("/api/paper-fund/start", json={"starting_cash": "100000", "duration_days": 7})
            self.assertEqual(bad.status_code, 422)
            started = await client.post("/api/paper-fund/start", json={"starting_cash": "10000", "duration_days": 7},
                                       headers={"Idempotency-Key": "api-start"})
            self.assertEqual(started.status_code, 200, started.text)
            run_id = started.json()["run"]["id"]
            self.assertEqual(D(started.json()["run"]["starting_cash"]), D("10000"))
            app.dependency_overrides[require_capital_user] = lambda: AuthenticatedUser(id="other-user", email=None)
            hidden = await client.get(f"/api/paper-fund?run_id={run_id}")
            self.assertIsNone(hidden.json()["run"])
            missing = await client.post("/api/paper-fund/pause")
            self.assertEqual(missing.status_code, 409)

    async def test_concurrent_withdrawals_cannot_overdraw_capital_ledger(self):
        async with self.factory() as session:
            portfolio = await get_or_create_default_portfolio(session, self.user)
            self.assertEqual(portfolio.initial_capital, D("10000"))

        async def withdraw(key):
            async with self.factory() as session:
                return await create_cash_withdrawal(session, CashWithdrawalCreate(
                    amount=D("6000"), currency="USD", platform="audit", entry_date=date.today(), idempotency_key=key), self.user)

        results = await asyncio.gather(withdraw("a"), withdraw("b"), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, CapitalValidationError) for result in results), 1, results)
        from app.services.portfolio.operating_core import cash_balance_in_base
        async with self.factory() as session:
            self.assertEqual(await cash_balance_in_base(session, portfolio), D("4000"))

    async def test_older_quote_cannot_overwrite_newer_live_mark(self):
        from app.services.market_data.ingestion import persist_quotes
        from app.services.market_data.quote_provider import LiveQuote
        async with self.factory() as session:
            instrument = Instrument(ticker="FRESH", name="Fresh", asset_class="equity", currency="USD")
            session.add(instrument)
            await session.flush()
            at = datetime.now(timezone.utc) - timedelta(seconds=2)
            universe = {"FRESH": [instrument.id]}
            await persist_quotes(session, universe, {"FRESH": LiveQuote(ticker="FRESH", price=D("120"), source="fmp", as_of=at)})
            await session.commit()
            await persist_quotes(session, universe, {"FRESH": LiveQuote(ticker="FRESH", price=D("99"), source="fmp", as_of=at - timedelta(minutes=1))})
            await session.commit()
            quote = await session.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument.id))
            self.assertEqual(quote.price, D("120"))
            self.assertEqual(quote.as_of, at)

    async def test_period_attribution_uses_opening_cash_and_historical_marks(self):
        from app.services.attribution.performance import build_attribution_report
        async with self.factory() as session:
            portfolio = await get_or_create_default_portfolio(session, self.user)
            opening_cash = await session.scalar(select(CashLedgerEntry).where(CashLedgerEntry.portfolio_id == portfolio.id))
            opening_cash.entry_date = date(2026, 9, 1)
            instrument = Instrument(ticker="REPORT", name="Report", asset_class="equity", currency="USD")
            session.add(instrument)
            await session.flush()
            session.add_all([
                Trade(portfolio_id=portfolio.id, instrument_id=instrument.id, trade_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
                      side="buy", status="filled", quantity=D("10"), executed_price=D("100"), fees=D("0"), rationale="fixture"),
                CashLedgerEntry(portfolio_id=portfolio.id, entry_date=date(2026, 9, 1), amount=D("-1000"), currency="USD", entry_type="trade_buy"),
                Position(portfolio_id=portfolio.id, instrument_id=instrument.id, quantity=D("10"), average_cost=D("100"),
                         market_value=D("2000"), unrealized_pnl=D("1000"), opened_at=datetime(2026, 9, 1, tzinfo=timezone.utc)),
                MarketPriceBar(instrument_id=instrument.id, bar_date=date(2026, 9, 30), source="test", close_price=D("110"), currency="USD"),
                MarketPriceBar(instrument_id=instrument.id, bar_date=date(2026, 10, 1), source="test", close_price=D("120"), currency="USD"),
            ])
            await session.commit()
            report = await build_attribution_report(session, self.user, period_start=date(2026, 10, 1), period_end=date(2026, 10, 2))
            self.assertEqual(report.summary.nav, D("10200"))
            self.assertEqual(report.summary.cash_balance, D("9000"))
            self.assertEqual(report.summary.net_pnl, D("100"))
            self.assertEqual(report.summary.reconciliation_gap, 0)
            self.assertEqual(report.summary.total_return_pct, D("0.99"))
