"""Radar transaction regressions against an explicitly supplied disposable DB.

HF_TEST_DATABASE_URL=postgresql+asyncpg://... python -m unittest tests.integration.test_radar_transactions -v
"""

import asyncio
import os
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.models import (
    Base,
    Instrument,
    InstrumentQuote,
    MarketPriceBar,
    RadarRun,
    RadarSnapshot,
    RadarUniverseMember,
)
from app.services.market_data.quote_provider import LiveQuote
from app.services.market_radar.catalog import SeedMember
from app.services.market_radar.runner import RadarScanInProgress, run_locked_radar_scan
from app.services.market_radar.scan import run_radar_scan
from app.services.market_radar.watchlist import AlwaysWatchedSet


TEST_URL = os.environ.get("HF_TEST_DATABASE_URL")
D = Decimal


@skipUnless(TEST_URL, "Set HF_TEST_DATABASE_URL to a disposable PostgreSQL database.")
class PostgresRadarTransactionTests(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = f"hf_radar_{uuid4().hex}"
        self.engine_options = {
            "connect_args": {"server_settings": {"search_path": self.schema}}
        }
        self.engine = create_async_engine(TEST_URL, **self.engine_options)
        async with self.engine.begin() as connection:
            await connection.execute(CreateSchema(self.schema))
            await connection.run_sync(Base.metadata.create_all)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False, autoflush=False)
        self.now = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.old = self.now - timedelta(hours=1)
        self.seeds = {
            "RADARTEST": SeedMember("RADARTEST", "US test", "US", "Technology", "Software"),
            "RADARTEST.NG": SeedMember(
                "RADARTEST.NG", "NG test", "NG", "Financial Services", "Banks",
                exchange="NGX", currency="NGN",
            ),
        }
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.publish_log = self.patches.enter_context(patch(
            "app.services.market_radar.scan.publish_system_log", new=AsyncMock()
        ))
        self.patches.enter_context(patch(
            "app.services.market_radar.catalog._seed_members", return_value=self.seeds
        ))
        self.patches.enter_context(patch(
            "app.services.market_radar.scan.load_always_watched",
            new=AsyncMock(return_value=AlwaysWatchedSet({})),
        ))
        self.fetch_us = self.patches.enter_context(patch(
            "app.services.market_radar.scan.fetch_us_movers",
            new=AsyncMock(return_value=([], 1, [])),
        ))
        self.fetch_ng = self.patches.enter_context(patch(
            "app.services.market_radar.scan.fetch_ngn_discovery",
            new=AsyncMock(return_value=([], 1, [])),
        ))
        self.fetch_quotes = self.patches.enter_context(patch(
            "app.services.market_radar.scan.fetch_quotes",
            new=AsyncMock(side_effect=self.quotes_for),
        ))
        async with self.factory() as session:
            prior = RadarRun(
                started_at=self.old, finished_at=self.old, status="completed",
                working_set_count=2, jurisdictions_scanned=["US", "NG"],
            )
            session.add(prior)
            await session.flush()
            for ticker, seed in self.seeds.items():
                instrument = Instrument(
                    ticker=ticker, name=seed.name, currency=seed.currency,
                    asset_class="equity", exchange=seed.exchange,
                )
                session.add(instrument)
                await session.flush()
                session.add_all([
                    InstrumentQuote(
                        instrument_id=instrument.id, price=D("100"), previous_close=D("95"),
                        currency=seed.currency, source="fmp", as_of=self.old, is_stale=False,
                    ),
                    RadarUniverseMember(
                        ticker=ticker, name="Old catalog name", jurisdiction=seed.jurisdiction,
                        currency=seed.currency, source=seed.source, source_rank=100,
                        is_active=True, last_synced_at=self.old,
                    ),
                    RadarSnapshot(
                        run_id=prior.id, ticker=ticker, name=seed.name,
                        jurisdiction=seed.jurisdiction, currency=seed.currency,
                        source="fmp", price=D("100"), as_of=self.old,
                        source_as_of=self.old, in_working_set=True,
                    ),
                ])
            await session.commit()

    async def asyncTearDown(self):
        async with self.engine.begin() as connection:
            await connection.execute(DropSchema(self.schema, cascade=True))
        await self.engine.dispose()

    def quotes_for(self, tickers):
        return {
            ticker: LiveQuote(
                ticker=ticker, price=D("105"), previous_close=D("100"),
                change_pct=D("5"), volume=1000000, as_of=self.now,
                source="ngnmarket" if ticker.endswith(".NG") else "fmp",
                currency=self.seeds[ticker].currency,
                raw_payload={"timestamp": int(self.now.timestamp())},
            )
            for ticker in tickers
        }

    async def assert_no_publication(self, *, failed_runs=0):
        """Observe committed state from a different database session."""
        async with self.factory() as observer:
            self.assertEqual(await observer.scalar(select(func.count()).select_from(Instrument)), 2)
            self.assertEqual(await observer.scalar(select(func.count()).select_from(RadarRun)), 1 + failed_runs)
            self.assertEqual(await observer.scalar(select(func.count()).select_from(RadarSnapshot)), 2)
            self.assertEqual(await observer.scalar(select(func.count()).select_from(MarketPriceBar)), 0)
            self.assertEqual(list(await observer.scalars(select(InstrumentQuote.price))), [D("100"), D("100")])

    async def assert_catalog_prepared(self):
        async with self.factory() as observer:
            members = list(await observer.scalars(select(RadarUniverseMember)))
            self.assertEqual(len(members), 2)
            for member in members:
                self.assertEqual(member.name, self.seeds[member.ticker].name)
                self.assertGreater(member.last_synced_at, self.old)

    async def update_catalog_from_another_session(self):
        async with self.factory() as writer:
            await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await writer.execute(update(RadarUniverseMember).where(
                RadarUniverseMember.ticker == "RADARTEST"
            ).values(name="Concurrent catalog update"))
            await writer.commit()

    async def test_all_vendor_callbacks_run_without_a_scan_transaction(self):
        calls = []
        async with self.factory() as session:
            async def check_callback(label):
                self.assertFalse(session.in_transaction(), label)
                self.assertFalse(session.new, label)
                self.assertFalse(session.dirty, label)
                await self.assert_no_publication()
                await self.assert_catalog_prepared()
                calls.append(label)

            async def us_discovery():
                await check_callback("US discovery")
                return [], 1, []

            async def ng_discovery():
                await check_callback("NG discovery")
                return [], 1, []

            async def quotes(tickers):
                await check_callback("NG quotes" if tickers[0].endswith(".NG") else "US quotes")
                return self.quotes_for(tickers)

            self.fetch_us.side_effect = us_discovery
            self.fetch_ng.side_effect = ng_discovery
            self.fetch_quotes.side_effect = quotes
            run = await run_radar_scan(session, jurisdictions=["US", "NG"], force=True)
            self.assertEqual(run.status, "completed", run.errors)
            self.assertEqual(calls, ["US discovery", "US quotes", "NG discovery", "NG quotes"])
            self.assertFalse(session.in_transaction())
        async with self.factory() as observer:
            self.assertEqual(await observer.scalar(select(func.count()).select_from(RadarSnapshot)), 4)
            self.assertEqual(list(await observer.scalars(select(InstrumentQuote.price))), [D("105"), D("105")])

    async def test_catalog_update_is_not_blocked_by_slow_discovery(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_discovery():
            entered.set()
            await release.wait()
            return [], 1, []

        self.fetch_us.side_effect = slow_discovery
        async with self.factory() as session:
            task = asyncio.create_task(run_radar_scan(session, jurisdictions=["US"], force=True))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                await asyncio.wait_for(self.update_catalog_from_another_session(), timeout=3)
            finally:
                release.set()
                run = await asyncio.wait_for(task, timeout=5)
            self.assertEqual(run.status, "completed", run.errors)
        async with self.factory() as observer:
            self.assertEqual(await observer.scalar(select(RadarUniverseMember.name).where(
                RadarUniverseMember.ticker == "RADARTEST"
            )), "Concurrent catalog update")

    async def test_live_notification_runs_after_scan_results_commit(self):
        async with self.factory() as session:
            async def publish(entry):
                self.assertFalse(session.in_transaction())
                self.assertEqual(entry.event, "radar_scan_completed")
                async with self.factory() as observer:
                    self.assertEqual(await observer.scalar(
                        select(func.count()).select_from(RadarSnapshot)
                    ), 4)
            self.publish_log.side_effect = publish
            run = await run_radar_scan(session, jurisdictions=["US", "NG"], force=True)
            self.assertEqual(run.status, "completed", run.errors)
            self.publish_log.assert_awaited_once()

    async def test_later_jurisdiction_failure_keeps_only_catalog_and_failed_audit(self):
        async def fail_ng_discovery():
            await self.assert_no_publication()
            self.assertEqual(self.fetch_quotes.await_count, 1)
            raise RuntimeError("simulated second-jurisdiction provider failure")

        self.fetch_ng.side_effect = fail_ng_discovery
        async with self.factory() as session:
            with patch("app.services.market_radar.scan.logger.exception"):
                run = await run_radar_scan(session, jurisdictions=["US", "NG"], force=True)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.errors[-1]["error"], "RuntimeError")
            self.assertEqual(run.working_set_count, 0)
            self.assertFalse(session.in_transaction())
        self.publish_log.assert_not_awaited()
        await self.assert_no_publication(failed_runs=1)
        await self.assert_catalog_prepared()

    async def test_publication_database_error_rolls_back_quotes_bars_and_snapshots(self):
        async def fail_after_publication(session, candidates):
            await session.flush()
            self.assertEqual(await session.scalar(select(func.count()).select_from(RadarSnapshot)), 4)
            self.assertEqual(await session.scalar(select(func.count()).select_from(MarketPriceBar)), 2)
            await session.execute(text("SELECT 1 / 0"))

        async with self.factory() as session:
            with patch("app.services.market_radar.scan._annotate_queue_tape_moves", new=fail_after_publication), \
                 patch("app.services.market_radar.scan.logger.exception"):
                run = await run_radar_scan(session, jurisdictions=["US", "NG"], force=True)
            self.assertEqual(run.status, "failed")
            self.assertEqual(run.errors[-1]["error"], "DBAPIError")
            self.assertFalse(session.in_transaction())
        await self.assert_no_publication(failed_runs=1)
        await self.assert_catalog_prepared()

    async def test_cancellation_rolls_back_publication_and_releases_quote_locks(self):
        entered = asyncio.Event()

        async def pause_after_publication(session, candidates):
            await session.flush()
            self.assertEqual(await session.scalar(select(func.count()).select_from(RadarSnapshot)), 4)
            entered.set()
            await asyncio.Event().wait()

        async with self.factory() as session:
            with patch("app.services.market_radar.scan._annotate_queue_tape_moves", new=pause_after_publication):
                task = asyncio.create_task(run_radar_scan(session, jurisdictions=["US", "NG"], force=True))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=5)
                finally:
                    task.cancel()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
            self.assertFalse(session.in_transaction())
            await self.assert_no_publication()
            async with self.factory() as writer:
                await writer.execute(text("SET LOCAL lock_timeout = '500ms'"))
                await writer.execute(update(InstrumentQuote).values(price=D("101")))
                await writer.commit()
        await self.assert_catalog_prepared()

    async def test_shared_lock_survives_scan_commits_and_releases_on_completion(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_discovery():
            entered.set()
            await release.wait()
            return [], 1, []

        self.fetch_us.side_effect = slow_discovery
        other_engine = create_async_engine(TEST_URL, **self.engine_options)
        other_factory = async_sessionmaker(other_engine, expire_on_commit=False, autoflush=False)
        try:
            async with self.factory() as first, other_factory() as second:
                task = asyncio.create_task(run_locked_radar_scan(first, jurisdictions=["US"], force=True))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=5)
                    # Catalog and candidate-read commits have already happened.
                    self.assertFalse(first.in_transaction())
                    await self.assert_catalog_prepared()
                    with self.assertRaises(RadarScanInProgress):
                        await asyncio.wait_for(run_locked_radar_scan(second, jurisdictions=["US"], force=True), timeout=3)
                    self.assertEqual(self.fetch_us.await_count, 1)
                finally:
                    release.set()
                    run = await asyncio.wait_for(task, timeout=5)
                self.assertEqual(run.status, "completed", run.errors)
                following = await run_locked_radar_scan(second, jurisdictions=["US"], force=True)
                self.assertEqual(following.status, "completed", following.errors)
        finally:
            await other_engine.dispose()

    async def test_cancelling_locked_scan_allows_the_next_scan(self):
        entered = asyncio.Event()

        async def slow_discovery():
            entered.set()
            await asyncio.Event().wait()

        self.fetch_us.side_effect = slow_discovery
        async with self.factory() as first, self.factory() as second:
            task = asyncio.create_task(run_locked_radar_scan(first, jurisdictions=["US"], force=True))
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
            self.assertFalse(first.in_transaction())
            await self.assert_no_publication()
            self.fetch_us.side_effect = None
            run = await run_locked_radar_scan(second, jurisdictions=["US"], force=True)
            self.assertEqual(run.status, "completed", run.errors)
