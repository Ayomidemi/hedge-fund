"""Run only against an explicitly supplied, migrated disposable PostgreSQL DB.

HF_TEST_DATABASE_URL=postgresql+asyncpg://... python -m unittest tests.integration.test_paper_fund_postgres -v
"""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import func, select, text
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

    async def test_order_expires_with_original_source_signal(self):
        instrument_id, radar_id = await self.seed_signal()
        async with self.factory() as session:
            snapshot = await session.scalar(select(RadarSnapshot).where(RadarSnapshot.run_id == radar_id))
            snapshot.source_as_of = NOW - timedelta(minutes=14)
            await session.commit()
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle()
        self.assertEqual(queued.orders[0].expires_at, NOW + timedelta(minutes=1))
        await self.quote(instrument_id, "100", NOW + timedelta(minutes=1))
        expired = await self.call_cycle(NOW + timedelta(minutes=1))
        self.assertEqual(expired.orders[0].status, "expired")
        self.assertEqual(expired.run.cash_balance, D("10000"))

    async def test_paper_orders_stay_on_radar_until_the_position_closes(self):
        from app.services.market_radar.watchlist import load_always_watched
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle()
        ticker = queued.orders[0].ticker
        async with self.factory() as session:
            candidate = (await load_always_watched(session)).candidates[ticker]
            self.assertTrue(candidate.in_opportunity_queue)
            self.assertTrue(candidate.always_watched)
            self.assertFalse(candidate.in_portfolio)
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        await self.call_cycle(at)
        async with self.factory() as session:
            candidate = (await load_always_watched(session)).candidates[ticker]
            self.assertTrue(candidate.in_portfolio)
            self.assertFalse(candidate.in_opportunity_queue)
        at += timedelta(seconds=30)
        await self.quote(instrument_id, "107", at)
        await self.call_cycle(at)
        async with self.factory() as session:
            self.assertNotIn(ticker, (await load_always_watched(session)).candidates)

    async def test_overview_during_fill_cannot_report_phantom_profit(self):
        from app.services.paper_fund import engine as paper_engine
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        await self.call_cycle()
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        original_orders = paper_engine._orders
        writer = None
        async with self.factory() as reader:
            async def orders_with_concurrent_fill(session, run):
                nonlocal writer
                if session is reader:
                    writer = asyncio.create_task(self.call_cycle(at))
                    # Give the competing transaction a chance to commit. A
                    # coherent reader holds it until all balances are read.
                    await asyncio.wait({writer}, timeout=0.2)
                return await original_orders(session, run)
            with patch.object(paper_engine, "_orders", orders_with_concurrent_fill):
                report = await overview(reader, self.owner, now=at)
        await asyncio.wait_for(writer, timeout=5)
        self.assertEqual(report.run.total_pnl, report.run.realized_pnl + report.run.unrealized_pnl)
        self.assertEqual(report.run.equity, D("10000"))
        self.assertEqual(report.orders[0].status, "pending")

    async def test_reused_session_refreshes_cash_orders_and_quotes(self):
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        await self.call_cycle()
        async with self.factory() as reader:
            old_run = await reader.scalar(select(PaperFundRun).where(PaperFundRun.owner_user_id == self.owner))
            old_order = await reader.scalar(select(PaperOrder).where(PaperOrder.run_id == old_run.id))
            old_quote = await reader.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument_id))
            await reader.commit()
            at = NOW + timedelta(seconds=30)
            await self.quote(instrument_id, "100", at)
            filled = await self.call_cycle(at)
            report = await overview(reader, self.owner, now=at)
            self.assertEqual(report.run.cash_balance, filled.run.cash_balance)
            self.assertEqual(report.orders[0].status, "open")
            await reader.commit()
            at += timedelta(seconds=30)
            await self.quote(instrument_id, "107", at)
            closed = await cycle(reader, self.owner, now=at)
            self.assertEqual(closed.orders[0].status, "closed")
            self.assertEqual(closed.run.total_pnl, closed.run.realized_pnl)
            self.assertEqual(old_quote.price, D("107"))
            self.assertEqual(old_order.status, "closed")

    async def test_job_lock_survives_job_commits_and_releases_after_failure(self):
        from app.db.locks import JOB_LOCK_NAMESPACE, hold_job_lock
        key = 7_100_001
        with self.assertRaisesRegex(RuntimeError, "job failed"):
            async with hold_job_lock(self.engine, key) as acquired:
                self.assertTrue(acquired)
                async with self.factory() as session:
                    await session.execute(text("SELECT 1"))
                    await session.commit()
                    # A live transaction pins the server connection even behind
                    # a transaction pooler; a session lock followed by commit
                    # leaves this NULL and can be stranded on another backend.
                    pinned = await session.scalar(text("""
                        SELECT a.xact_start IS NOT NULL
                        FROM pg_locks AS l JOIN pg_stat_activity AS a ON a.pid = l.pid
                        WHERE l.locktype = 'advisory' AND l.classid = :namespace
                          AND l.objid = :key AND l.granted
                    """), {"key": key, "namespace": JOB_LOCK_NAMESPACE})
                    self.assertTrue(pinned)
                async with hold_job_lock(self.engine, key) as duplicate:
                    self.assertFalse(duplicate)
                raise RuntimeError("job failed")
        async with hold_job_lock(self.engine, key) as reacquired:
            self.assertTrue(reacquired)

    async def test_legacy_pooler_session_lock_cannot_strand_new_worker(self):
        from app.db.locks import hold_job_lock
        key = 7_100_002
        async with self.engine.connect() as legacy_connection:
            self.assertTrue(await legacy_connection.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}))
            await legacy_connection.commit()
            try:
                async with hold_job_lock(self.engine, key) as acquired:
                    self.assertTrue(acquired)
            finally:
                await legacy_connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
                await legacy_connection.commit()

    async def test_backdated_cycle_cannot_rewind_heartbeat(self):
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        later = NOW + timedelta(minutes=1)
        await self.call_cycle(later)
        report = await self.call_cycle(NOW)
        self.assertEqual(report.run.last_cycle_at, later)

    async def test_capital_dashboard_read_blocks_partial_trade_visibility(self):
        from app.db.locks import lock_portfolio
        from app.models import Portfolio
        from app.services.portfolio import operating_core
        async with self.factory() as session:
            portfolio = await get_or_create_default_portfolio(session, self.user)
            instrument = Instrument(ticker="CONSISTENT", name="Read race", asset_class="equity", currency="USD")
            session.add(instrument)
            await session.commit()
            portfolio_id, instrument_id = portfolio.id, instrument.id

        async def book_position():
            async with self.factory() as session:
                portfolio = await session.get(Portfolio, portfolio_id)
                await lock_portfolio(session, portfolio)
                session.add_all([
                    CashLedgerEntry(portfolio_id=portfolio_id, entry_date=date.today(), amount=-1000,
                                    currency="USD", entry_type="trade_buy"),
                    Position(portfolio_id=portfolio_id, instrument_id=instrument_id, quantity=10,
                             average_cost=100, market_value=1000, unrealized_pnl=0, opened_at=NOW),
                ])
                await session.commit()

        original_cash = operating_core._list_cash_entries
        writer = None
        async with self.factory() as reader:
            async def cash_with_concurrent_trade(session, portfolio_id):
                nonlocal writer
                entries = await original_cash(session, portfolio_id)
                if session is reader:
                    writer = asyncio.create_task(book_position())
                    await asyncio.wait({writer}, timeout=0.2)
                return entries
            with patch.object(operating_core, "_list_cash_entries", cash_with_concurrent_trade):
                dashboard = await operating_core.get_dashboard(reader, self.user)
        await asyncio.wait_for(writer, timeout=5)
        self.assertEqual(dashboard.nav, D("10000"))
        self.assertEqual(dashboard.open_position_count, 0)

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
