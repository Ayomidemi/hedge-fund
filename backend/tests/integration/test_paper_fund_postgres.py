"""Run only against an explicitly supplied, migrated disposable PostgreSQL DB.

HF_TEST_DATABASE_URL=postgresql+asyncpg://... python -m unittest tests.integration.test_paper_fund_postgres -v
"""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest import IsolatedAsyncioTestCase, skipUnless
from unittest.mock import patch, AsyncMock
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

    async def seed_signal(self, *, radar_id=None, stock_cap="10"):
        ticker = "TEST" + uuid4().hex[:10].upper()
        async with self.factory() as session:
            from app.models import RiskLimit
            portfolio = await get_or_create_default_portfolio(session, self.user)
            # This fixture explicitly permits the original 10% sizing policy;
            # default-account limits are tested separately below.
            limit = await session.scalar(select(RiskLimit).where(RiskLimit.portfolio_id == portfolio.id,
                RiskLimit.limit_type == "max_single_equity_position_pct"))
            limit.threshold_value = D(stock_cap)
            instrument = Instrument(ticker=ticker, name="Paper test", currency="USD", asset_class="equity", sector="Technology",
                industry="Software", execution_metadata={"source":"fmp_profile", "symbol":ticker, "product_type":"equity",
                                                         "currency":"USD", "checked_at":NOW.isoformat()})
            run = await session.get(RadarRun, radar_id) if radar_id else RadarRun(started_at=NOW, finished_at=NOW, status="completed")
            session.add_all([instrument, run])
            await session.flush()
            history_date = NOW.date() - timedelta(days=1)
            for index in range(260):
                while history_date.weekday() >= 5:
                    history_date -= timedelta(days=1)
                close = D("100") + D(index % 3) / 100
                session.add(MarketPriceBar(instrument_id=instrument.id, bar_date=history_date, source="tiingo",
                    close_price=close, adjusted_close_price=close, volume=1000000, currency="USD"))
                history_date -= timedelta(days=1)
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

    async def fresh_signal(self, instrument_id, at):
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            old = await session.scalar(select(RadarSnapshot).where(RadarSnapshot.ticker == instrument.ticker)
                                       .order_by(RadarSnapshot.as_of.desc()).limit(1))
            values = {col.name: getattr(old, col.name) for col in RadarSnapshot.__table__.columns
                      if col.name not in {'id','created_at','updated_at','run_id'}}
            run = RadarRun(started_at=at, finished_at=at, status='completed', working_set_count=1)
            session.add(run)
            await session.flush()
            values.update(as_of=at, source_as_of=at, run_id=run.id)
            snapshot = RadarSnapshot(**values)
            session.add(snapshot)
            await session.commit()
            return snapshot.id

    async def test_radar_history_excludes_current_future_and_duplicate_sources(self):
        from app.services.market_radar.scan import _apply_historical_evidence
        from app.services.market_radar.scoring import RadarCandidate
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            original = RadarCandidate(ticker=instrument.ticker, name='Test', jurisdiction='US',
                                      change_pct=D('5'), price=D('105'), volume=2000000)
            await _apply_historical_evidence(session, [original], now=NOW)
            for day, source in ((NOW.date(), 'tiingo'), (NOW.date()+timedelta(days=1), 'tiingo'),
                                (NOW.date()-timedelta(days=1), 'live'), (NOW.date()-timedelta(days=1), 'yahoo')):
                session.add(MarketPriceBar(instrument_id=instrument_id, bar_date=day, source=source,
                    close_price=D('1000'), adjusted_close_price=D('1000'), volume=99999999, currency='USD'))
            await session.flush()
            actual = RadarCandidate(ticker=instrument.ticker, name='Test', jurisdiction='US',
                                    change_pct=D('5'), price=D('105'), volume=2000000)
            await _apply_historical_evidence(session, [actual], now=NOW)
            for key in ('bar_count', 'price_return_zscore', 'average_volume', 'avg_dollar_volume'):
                self.assertEqual(actual.evidence[key], original.evidence[key], key)

    async def test_retired_book_name_loses_protected_radar_membership(self):
        from app.models import RadarUniverseMember
        from app.services.market_radar.catalog import sync_monitored_universe
        from app.services.market_radar.watchlist import AlwaysWatchedSet
        from app.services.market_radar.scan import _pin_prior_working_set
        instrument_id, radar_id = await self.seed_signal()
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            member = RadarUniverseMember(ticker=instrument.ticker, name='Retired', jurisdiction='US',
                source='book', source_rank=10, asset_class='equity', currency='USD', is_active=True,
                always_watched=True, member_metadata={}, last_synced_at=NOW)
            session.add(member)
            await session.flush()
            await sync_monitored_universe(session, watched=AlwaysWatchedSet({}))
            self.assertFalse(member.always_watched)
            self.assertTrue(member.is_active)
            radar = await session.get(RadarRun, radar_id)
            radar.working_set_count = 1
            snapshot = await session.scalar(select(RadarSnapshot).where(RadarSnapshot.run_id == radar_id))
            snapshot.in_working_set = snapshot.always_watched = True
            await session.flush()
            candidates = {}
            await _pin_prior_working_set(session, candidates, jurisdictions=['US'])
            self.assertTrue(candidates[instrument.ticker].pinned_prior)
            self.assertFalse(candidates[instrument.ticker].always_watched)

    async def test_radar_scan_persists_observation_quality_without_creating_orders(self):
        from app.services.market_radar.scan import run_radar_scan
        from app.services.market_radar.scoring import RadarCandidate
        from app.services.market_radar.catalog import CatalogSyncResult
        from app.services.market_radar.watchlist import AlwaysWatchedSet
        from app.services.market_data.quote_provider import LiveQuote
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            verified = RadarCandidate(ticker=instrument.ticker, name='Test', jurisdiction='US')
            discovery = RadarCandidate(ticker='UNVERIFIED', name='Discovery', jurisdiction='US',
                source='fmp', price=D('10'), change_pct=D('90'), flags=['unusual_volume'], source_as_of=NOW)
            clock = type('Clock', (datetime,), {'now':classmethod(lambda cls, tz=None: NOW)})
            live = LiveQuote(ticker=instrument.ticker, price=D('105'), previous_close=D('100'),
                change_pct=D('5'), volume=3000000, as_of=NOW, source='fmp',
                raw_payload={'timestamp':int(NOW.timestamp())})
            with patch('app.services.market_radar.scan.datetime', clock), \
                 patch('app.services.market_radar.scan.load_always_watched', new=AsyncMock(return_value=AlwaysWatchedSet({}))), \
                 patch('app.services.market_radar.scan.sync_monitored_universe', new=AsyncMock(return_value=CatalogSyncResult(1,0,0,0))), \
                 patch('app.services.market_radar.scan.load_catalog_candidates', new=AsyncMock(return_value=[verified])), \
                 patch('app.services.market_radar.scan.fetch_us_movers', new=AsyncMock(return_value=([discovery],3,[]))), \
                 patch('app.services.market_radar.scan.fetch_quotes', new=AsyncMock(return_value={instrument.ticker:live})), \
                 patch('app.services.market_radar.scan.record_system_log', new=AsyncMock()):
                radar = await run_radar_scan(session, jurisdictions=['US'])
            self.assertEqual(radar.status, 'completed', radar.errors)
            self.assertTrue(any(note.startswith('Coverage:') for note in radar.notes))
            rows = {row.ticker:row for row in await session.scalars(select(RadarSnapshot).where(RadarSnapshot.run_id == radar.id))}
            self.assertEqual(rows[instrument.ticker].evidence['observation_quality'], 'verified_timestamp')
            self.assertEqual(rows['UNVERIFIED'].evidence['observation_quality'], 'unverified')
            self.assertIsNone(rows['UNVERIFIED'].radar_priority)
            self.assertNotIn('unusual_volume', rows['UNVERIFIED'].flags)
            self.assertEqual(await session.scalar(select(func.count()).select_from(PaperOrder)), 0)

    async def call_cycle(self, at=NOW):
        async with self.factory() as session:
            return await cycle(session, self.owner, now=at)

    async def test_failed_radar_scan_rolls_back_partial_writes_and_recovers_session(self):
        from app.services.market_radar.scan import run_radar_scan
        from app.services.market_radar.catalog import CatalogSyncResult
        from app.services.market_radar.scoring import RadarCandidate
        from app.services.market_radar.watchlist import AlwaysWatchedSet
        instrument_id, _ = await self.seed_signal()
        for database_failure in (False, True):
            with self.subTest(database_failure=database_failure):
                async with self.factory() as session:
                    quote = await session.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument_id))
                    before_runs = await session.scalar(select(func.count()).select_from(RadarRun))
                    before_rows = await session.scalar(select(func.count()).select_from(RadarSnapshot))
                    async def staged_write(*args, **kwargs):
                        quote.price = D('999')
                        await session.flush()
                        return 1
                    async def fail_after_snapshots(*args, **kwargs):
                        await session.flush()
                        self.assertGreater(await session.scalar(select(func.count()).select_from(RadarSnapshot)), before_rows)
                        if database_failure:
                            await session.execute(text('SELECT 1 / 0'))
                        raise RuntimeError('simulated failure after snapshot publication')
                    with patch('app.services.market_radar.scan.load_always_watched', new=AsyncMock(return_value=AlwaysWatchedSet({}))), \
                         patch('app.services.market_radar.scan.sync_monitored_universe', new=AsyncMock(return_value=CatalogSyncResult(1,0,0,0))), \
                         patch('app.services.market_radar.scan.load_catalog_candidates', new=AsyncMock(return_value=[RadarCandidate(ticker='BROKEN', name='Broken', jurisdiction='US')])), \
                         patch('app.services.market_radar.scan._pin_prior_working_set', new=AsyncMock()), \
                         patch('app.services.market_radar.scan._apply_cached_quotes', new=AsyncMock(return_value=0)), \
                         patch('app.services.market_radar.scan.fetch_us_movers', new=AsyncMock(return_value=([],0,[]))), \
                         patch('app.services.market_radar.scan._persist_vendor_tapes', new=staged_write), \
                         patch('app.services.market_radar.scan._annotate_queue_tape_moves', new=fail_after_snapshots), \
                         patch('app.services.market_radar.scan.logger.exception'):
                        run = await run_radar_scan(session, force=True, jurisdictions=['US'])
                    self.assertEqual(run.status, 'failed')
                    self.assertEqual(run.working_set_count, 0)
                    await session.refresh(quote)
                    self.assertEqual(quote.price, D('100'))
                    self.assertEqual(await session.scalar(select(func.count()).select_from(RadarRun)), before_runs + 1)
                    self.assertEqual(await session.scalar(select(func.count()).select_from(RadarSnapshot)), before_rows)
                    self.assertEqual(await session.scalar(select(func.count()).select_from(PaperOrder)), 0)
                    self.assertEqual(await session.scalar(select(func.count()).select_from(RadarRun).where(RadarRun.id == run.id)), 1)

    async def test_radar_overview_preserves_scan_evidence_and_excludes_stale_alerts(self):
        from app.services.market_radar.overview import build_radar_overview
        _, old_run_id = await self.seed_signal()
        _, run_id = await self.seed_signal()
        async with self.factory() as session:
            for radar_id in (old_run_id, run_id):
                run = await session.get(RadarRun, radar_id)
                run.working_set_count = 2
            current = await session.scalar(select(RadarSnapshot).where(RadarSnapshot.run_id == run_id))
            current.in_working_set = True
            current.flags = ['price_move']
            current.evidence = {**current.evidence, 'industry_status':'market_event', 'move_scope':'market'}
            for ticker, stale, working in (('STALE', 'old quote', True), ('OUTSIDE', None, False), ('QUIET', None, True)):
                session.add(RadarSnapshot(run_id=run_id, ticker=ticker, name=ticker, jurisdiction='US',
                    sector='Technology', currency='USD', asset_class='equity', source='fmp',
                    as_of=NOW, source_as_of=NOW, in_working_set=working, price=D('100'),
                    change_pct=D('6') if ticker != 'QUIET' else D('1'),
                    flags=['price_move'] if ticker != 'QUIET' else ['volatility_shift'],
                    radar_priority='P0' if ticker != 'QUIET' else None,
                    carried_forward=False, stale_reason=stale, evidence={}))
            await session.commit()
            result = await build_radar_overview(session)
            self.assertEqual(result.latest_run.id, run_id)
            self.assertEqual(result.flagged_count, 1)
            self.assertEqual(result.flagged[0].ticker, current.ticker)
            self.assertEqual(result.flagged[0].evidence['move_scope'], 'market')
            self.assertEqual(result.flagged[0].evidence['industry_status'], 'market_event')
            self.assertEqual(result.industries[0].flagged_count, 1)
            self.assertIsNone(next(row for row in result.working_set if row.ticker == 'STALE').radar_priority)

    async def test_compact_radar_preserves_observations_without_duplicate_payloads(self):
        from app.models import RadarWatchlistItem
        from app.services.market_radar.overview import build_radar_overview
        _, run_id = await self.seed_signal()
        async with self.factory() as session:
            run = await session.get(RadarRun, run_id)
            run.working_set_count = 1
            row = await session.scalar(select(RadarSnapshot).where(RadarSnapshot.run_id == run_id))
            row.in_working_set = True
            row.flags = ['price_move']
            row.sparkline = [{'price': '100'}, {'price': '101'}, {'price': '102'}]
            row.evidence = {'return_sample_count': 30, 'history_gap': False,
                            'on_watchlist': True, 'large_provider_detail': 'x' * 5000}
            ticker = row.ticker
            session.add(RadarWatchlistItem(owner_user_id=self.owner, ticker=ticker, name='Test', jurisdiction='US'))
            await session.commit()
        # Separate sessions ensure the compact query really works with its
        # deferred sparkline, rather than reusing a fully loaded ORM object.
        async with self.factory() as session:
            full = await build_radar_overview(session, owner_user_id=self.owner)
        async with self.factory() as session:
            with patch('app.services.market_radar.overview.list_watchlist',
                       AsyncMock(side_effect=AssertionError('Compact view must not load watchlist history'))):
                compact = await build_radar_overview(session, owner_user_id=self.owner, compact=True)
        self.assertEqual(compact.working_set_count, full.working_set_count)
        self.assertEqual(compact.flagged_count, full.flagged_count)
        self.assertEqual(compact.p1_count, full.p1_count)
        for a, b in zip(compact.working_set, full.working_set, strict=True):
            for key in ('ticker', 'price', 'radar_priority', 'priority_reasons', 'source_as_of',
                        'stale_reason', 'carried_forward', 'on_watchlist', 'in_portfolio'):
                self.assertEqual(getattr(a, key), getattr(b, key), key)
            self.assertEqual(a.evidence['return_sample_count'], 30)
            self.assertEqual(a.sparkline, [])
        self.assertTrue(compact.working_set[0].on_watchlist)
        self.assertEqual(compact.flagged, [])
        self.assertTrue(all(not industry.names for industry in compact.industries))
        self.assertLess(len(compact.model_dump_json()), len(full.model_dump_json()) / 2)
        async with self.factory() as session:
            other = await build_radar_overview(session, owner_user_id='another-owner', compact=True)
        self.assertFalse(other.working_set[0].on_watchlist)

    async def test_multiple_entries_fill_together_and_existing_positions_do_not_block_new_entries(self):
        first, radar_id = await self.seed_signal(stock_cap="5")
        second, _ = await self.seed_signal(radar_id=radar_id, stock_cap="5")
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle()
        self.assertEqual([o.status for o in queued.orders], ["pending", "pending"])
        self.assertGreater(queued.run.reserved_cash, 0)
        at = NOW + timedelta(seconds=30)
        for instrument_id in (first, second):
            await self.quote(instrument_id, "100", at)
        await asyncio.gather(self.call_cycle(at), self.call_cycle(at))
        opened = await self.call_cycle(at)
        self.assertEqual([o.status for o in opened.orders], ["open", "open"])
        self.assertEqual({o.opened_at for o in opened.orders}, {at})
        third, _ = await self.seed_signal(radar_id=radar_id, stock_cap="5")
        queued = await self.call_cycle(at)
        self.assertEqual(sum(o.status == "open" for o in queued.orders), 2)
        self.assertEqual(sum(o.status == "pending" for o in queued.orders), 1)
        at += timedelta(seconds=30)
        for instrument_id in (first, second, third):
            await self.quote(instrument_id, "100", at)
        opened = await self.call_cycle(at)
        self.assertEqual(sum(o.status == "open" for o in opened.orders), 3)
        self.assertEqual(opened.capital.open_position_count, 3)
        self.assertEqual(opened.run.reserved_cash, 0)
        self.assertEqual(opened.capital.trade_count, 3)
        expected_cash = D("10000") - sum(o.entry_price * o.quantity + o.fees_paid for o in opened.orders)
        self.assertEqual(opened.run.cash_balance, expected_cash)
        # One target exit leaves the other two positions independently active.
        at += timedelta(seconds=30)
        await self.quote(first, "107", at)
        closed = await self.call_cycle(at)
        self.assertEqual(sum(o.status == "closed" for o in closed.orders), 1)
        self.assertEqual(sum(o.status == "open" for o in closed.orders), 2)
        self.assertEqual(closed.capital.trade_count, 4)

    async def test_latest_radar_history_matches_queue_when_scan_start_times_tie(self):
        await self.seed_signal()
        newest, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        result = await self.call_cycle()
        self.assertEqual(len(result.orders), 1, result.blockers)
        async with self.factory() as session:
            order = await session.get(PaperOrder, result.orders[0].id)
            self.assertEqual(order.instrument_id, newest)

    async def test_stalled_history_read_rolls_back_and_releases_account_lock(self):
        await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        async def stalled(*args, **kwargs):
            await asyncio.sleep(10)
        with patch('app.services.paper_fund.engine.CYCLE_TIMEOUT_SECONDS', 0.2), \
             patch('app.services.risk.risk_centre._load_price_histories', new=stalled):
            async with self.factory() as session:
                with self.assertRaises(TimeoutError):
                    await cycle(session, self.owner, now=NOW)
                self.assertFalse(session.in_transaction())
                # Keep the timed-out session alive while a second session trades.
                with patch('app.services.paper_fund.engine.CYCLE_TIMEOUT_SECONDS', 5), \
                     patch('app.services.risk.risk_centre._load_price_histories', return_value={}):
                    result = await asyncio.wait_for(self.call_cycle(), timeout=3)
                self.assertEqual(result.run.cash_balance, D('10000'))
                self.assertEqual(result.orders, [])

    async def test_risk_history_loads_only_required_provider_fields(self):
        from app.services.risk.risk_centre import _load_price_histories
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            bar = await session.scalar(select(MarketPriceBar).where(
                MarketPriceBar.instrument_id == instrument_id).order_by(MarketPriceBar.bar_date.desc()))
            bar.raw_payload = {"close": 101, "unused_provider_data": "x" * 10000}
            await session.commit()
            histories = await _load_price_histories(session, [instrument], as_of=NOW.date())
            newest = histories[instrument.ticker][-1]
            self.assertEqual(newest.raw_payload, {"close": 101})
            self.assertEqual(newest.adjusted_close_price, bar.adjusted_close_price)
            self.assertEqual(newest.volume, 1000000)

    async def test_history_refresh_survives_rollback_after_timeout(self):
        from types import SimpleNamespace
        from app.services.paper_fund.history import refresh_risk_history
        _, radar_id = await self.seed_signal()
        async with self.factory() as session:
            for index in range(4):
                ticker = f'RETRY{index}'
                instrument = Instrument(ticker=ticker, name=ticker, currency='USD', asset_class='equity')
                session.add(instrument)
                session.add(RadarSnapshot(run_id=radar_id, ticker=ticker, name=ticker, jurisdiction='US',
                    currency='USD', asset_class='equity', source='fmp', price=D('100'), change_pct=D('5'),
                    as_of=NOW, source_as_of=NOW, radar_priority='P1', priority_score=D('90')))
            await session.commit()
        fetched = []
        async def fetch(session, instrument, start, **kwargs):
            fetched.append(instrument.ticker)
            if len(fetched) == 1:
                raise TimeoutError('simulated provider timeout')
            if len(fetched) == 2:
                raise ValueError('simulated malformed provider volume')
            return 5
        with patch('app.services.paper_fund.history.settings', SimpleNamespace(hf_tiingo_api_key='fixture')), \
             patch('app.services.paper_fund.history._fill_tiingo_daily', new=fetch):
            async with self.factory() as session:
                saved = await refresh_risk_history(session, now=NOW)
        self.assertEqual(len(fetched), 4)
        self.assertEqual(saved, 10)

    async def test_unranked_discoveries_and_catalog_names_prepare_without_existing_instruments(self):
        from types import SimpleNamespace
        from app.models import RadarHistoryPreparation, RadarUniverseMember
        from app.services.paper_fund.history import refresh_risk_history
        _, radar_id = await self.seed_signal()
        names = {f'NEW{i}' for i in range(7)} | {'CATALOG'}
        async with self.factory() as session:
            for ticker in names - {'CATALOG'}:
                session.add(RadarSnapshot(run_id=radar_id, ticker=ticker, name=ticker,
                    jurisdiction='US', currency='USD', asset_class='equity', source='fmp',
                    as_of=NOW, radar_priority=None, in_working_set=False))
            for ticker, jurisdiction, currency in (('CATALOG', 'US', 'USD'), ('NG.NG', 'NG', 'NGN')):
                session.add(RadarUniverseMember(ticker=ticker, name=ticker, jurisdiction=jurisdiction,
                    currency=currency, source='manual', last_synced_at=NOW))
            await session.commit()
        fetched = []
        async def fetch(session, instrument, start, **kwargs):
            fetched.append(instrument.ticker)
            if instrument.ticker == 'NEW0':
                raise TimeoutError('fixture')
            return 0
        with patch('app.services.paper_fund.history.settings', SimpleNamespace(hf_tiingo_api_key='fixture')), \
             patch('app.services.paper_fund.history._fill_tiingo_daily', new=fetch):
            for at in (NOW, NOW+timedelta(minutes=5)):
                async with self.factory() as session:
                    await refresh_risk_history(session, now=at)
            self.assertEqual(len(fetched), 8)
            self.assertEqual(set(fetched), names)
            # A new session/worker preserves retry timing; no repeated empty downloads.
            async with self.factory() as session:
                from sqlalchemy import event
                statements = []
                def capture(connection, cursor, statement, parameters, context, executemany):
                    statements.append(statement)
                event.listen(self.engine.sync_engine, 'before_cursor_execute', capture)
                try:
                    await refresh_risk_history(session, now=NOW+timedelta(minutes=10))
                finally:
                    event.remove(self.engine.sync_engine, 'before_cursor_execute', capture)
                self.assertFalse(any('market_price_bars' in statement for statement in statements))
                self.assertEqual(len(fetched), 8)
                state = await session.get(RadarHistoryPreparation, 'NEW0')
                self.assertEqual(state.last_seen_at, NOW)
                self.assertEqual(state.status, 'retry')
                self.assertEqual(state.last_error, 'TimeoutError')
                self.assertGreater(state.next_attempt_at, NOW+timedelta(minutes=10))
                self.assertEqual(await session.scalar(select(func.count()).select_from(PaperOrder)), 0)
                self.assertEqual(await session.scalar(select(func.count()).select_from(InstrumentQuote)), 1)

    async def test_prepared_history_enables_scoring_but_does_not_create_orders(self):
        from types import SimpleNamespace
        from app.models import RadarHistoryPreparation
        from app.services.paper_fund.history import refresh_risk_history
        from app.services.market_radar.scan import _apply_historical_evidence
        from app.services.market_radar.scoring import RadarCandidate
        _, radar_id = await self.seed_signal()
        async with self.factory() as session:
            session.add(RadarSnapshot(run_id=radar_id, ticker='UNRANKED', name='New', jurisdiction='US',
                currency='USD', asset_class='equity', source='fmp', as_of=NOW, radar_priority=None))
            await session.commit()
        async def fetch(session, instrument, start, **kwargs):
            day = NOW.date()-timedelta(days=1)
            for index in range(30):
                while day.weekday() >= 5:
                    day -= timedelta(days=1)
                session.add(MarketPriceBar(instrument_id=instrument.id, bar_date=day, source='tiingo',
                    close_price=D(100+index%3), adjusted_close_price=D(100+index%3), volume=10000, currency='USD'))
                day -= timedelta(days=1)
            await session.commit()
            return 30
        with patch('app.services.paper_fund.history.settings', SimpleNamespace(hf_tiingo_api_key='fixture')), \
             patch('app.services.paper_fund.history._fill_tiingo_daily', new=fetch):
            async with self.factory() as session:
                await refresh_risk_history(session, now=NOW)
                state = await session.get(RadarHistoryPreparation, 'UNRANKED')
                self.assertEqual(state.status, 'partial')
                self.assertEqual(state.bar_count, 30)
                self.assertEqual(state.next_attempt_at, NOW+timedelta(hours=12))
                item = RadarCandidate(ticker='UNRANKED', name='New', jurisdiction='US',
                                      change_pct=D('6'), volume=30000)
                await _apply_historical_evidence(session, [item], now=NOW)
                self.assertEqual(item.evidence['return_sample_count'], 29)
                self.assertIn('price_return_zscore', item.evidence)
                self.assertEqual(item.volume_ratio, D('3'))
                self.assertEqual(await session.scalar(select(func.count()).select_from(PaperOrder)), 0)

    async def test_history_download_preserves_raw_prices_and_excludes_invalid_dates(self):
        from app.services.market_radar.watchlist_book import _fill_tiingo_daily
        instrument_id, _ = await self.seed_signal()
        end = NOW.date()-timedelta(days=1)
        valid = {'date':end.isoformat(), 'close':100, 'adjClose':50, 'volume':1000}
        payload = [valid, valid, {**valid, 'date':NOW.date().isoformat()},
                   {**valid, 'date':(end-timedelta(days=1)).isoformat(), 'close':'NaN'},
                   {**valid, 'date':(end-timedelta(days=2)).isoformat(), 'volume':'Infinity'}]
        client = AsyncMock()
        client.get.return_value = httpx.Response(200, json=payload, request=httpx.Request('GET', 'https://example.test'))
        async with self.factory() as session:
            instrument = await session.get(Instrument, instrument_id)
            with patch('app.services.market_radar.watchlist_book.httpx.AsyncClient') as factory:
                factory.return_value.__aenter__.return_value = client
                saved = await _fill_tiingo_daily(session, instrument, end-timedelta(days=4), end=end)
            self.assertEqual(saved, 2)
            self.assertEqual(client.get.call_args.kwargs['params']['endDate'], end.isoformat())
            bar = await session.scalar(select(MarketPriceBar).where(MarketPriceBar.instrument_id == instrument_id,
                MarketPriceBar.bar_date == end, MarketPriceBar.source == 'tiingo'))
            self.assertEqual(bar.close_price, D('100'))
            self.assertEqual(bar.adjusted_close_price, D('50'))
            self.assertEqual(await session.scalar(select(func.count()).select_from(MarketPriceBar).where(
                MarketPriceBar.instrument_id == instrument_id, MarketPriceBar.bar_date == NOW.date())), 0)

    async def test_preparation_coverage_matches_radar_provider_precedence(self):
        from app.services.paper_fund.history import _coverage
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            before = (await _coverage(session, [instrument_id], NOW))[instrument_id]
            bar = await session.scalar(select(MarketPriceBar).where(MarketPriceBar.instrument_id == instrument_id)
                                       .order_by(MarketPriceBar.bar_date.desc()).limit(1))
            bar.adjusted_close_price = D('0')
            session.add(MarketPriceBar(instrument_id=instrument_id, source='yahoo', bar_date=bar.bar_date,
                close_price=D('100'), adjusted_close_price=D('100'), volume=10000, currency='USD'))
            for day in (NOW.date(), NOW.date()+timedelta(days=1)):
                session.add(MarketPriceBar(instrument_id=instrument_id, source='tiingo', bar_date=day,
                    close_price=D('100'), adjusted_close_price=D('100'), volume=10000, currency='USD'))
            await session.flush()
            after = (await _coverage(session, [instrument_id], NOW))[instrument_id]
            self.assertEqual(after[0], before[0]-1)
            self.assertLess(after[1], before[1])

    async def test_concurrent_risk_policy_creation_has_one_shared_version(self):
        from app.services.risk.risk_centre import _get_or_create_policy_version
        from app.services.risk.policy import profile_policy
        from app.models import RiskPolicyVersion
        barrier = asyncio.Barrier(2)
        async def capture():
            async with self.factory() as session:
                original_scalar = session.scalar
                calls = 0
                async def scalar(statement, *args, **kwargs):
                    nonlocal calls
                    calls += 1
                    result = await original_scalar(statement, *args, **kwargs)
                    if calls == 1:
                        await barrier.wait()
                    return result
                with patch.object(session, 'scalar', new=scalar):
                    policy = await _get_or_create_policy_version(session, profile_policy())
                    await session.commit()
                    return policy.id
        first, second = await asyncio.wait_for(asyncio.gather(capture(), capture()), timeout=10)
        self.assertEqual(first, second)
        async with self.factory() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(RiskPolicyVersion)), 1)

    async def test_profile_change_persists_cancels_and_reassesses_pending(self):
        from app.services.paper_fund.settings import risk_settings
        from app.models import Portfolio
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        before = await self.call_cycle()
        pending = next(o for o in before.orders if o.status == 'pending')
        with patch('app.services.administration.system_log.publish_event', new=AsyncMock()):
            async with self.factory() as session:
                saved = await risk_settings(session, self.owner, update='low', expected='medium')
                self.assertEqual(saved['profile'], 'low')
        async with self.factory() as session:
            portfolio = await session.scalar(select(Portfolio).where(Portfolio.owner_user_id == self.owner))
            self.assertEqual(portfolio.risk_profile, 'low')
            self.assertEqual(portfolio.trading_mode, 'automatic')
            cancelled = await session.get(PaperOrder, pending.id)
            self.assertEqual(cancelled.status, 'cancelled')
        unchanged = await self.call_cycle(NOW+timedelta(seconds=15))
        self.assertFalse(any(o.status == 'pending' for o in unchanged.orders))
        await self.fresh_signal(instrument_id, NOW+timedelta(seconds=30))
        after = await self.call_cycle(NOW+timedelta(seconds=30))
        queued = next(o for o in after.orders if o.status == 'pending')
        self.assertNotEqual(queued.id, pending.id)
        self.assertEqual(next(o for o in after.orders if o.id == pending.id).status, 'cancelled')
        self.assertLess(queued.quantity, pending.quantity)
        self.assertEqual(after.run.cash_balance, before.run.cash_balance)
        self.assertEqual(after.run.started_at, before.run.started_at)

    async def test_profile_change_cannot_clear_halt_or_widen_stop(self):
        from app.services.paper_fund.settings import risk_settings
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        await self.call_cycle()
        await self.quote(instrument_id, '100', NOW+timedelta(seconds=30))
        before = await self.call_cycle(NOW+timedelta(seconds=30))
        opened = next(o for o in before.orders if o.status == 'open')
        async with self.factory() as session:
            fund = await session.get(PaperFundRun, before.run.id)
            fund.status, fund.halt_reason = 'halted', 'Test halt'
            await session.commit()
        with patch('app.services.administration.system_log.publish_event', new=AsyncMock()):
            async with self.factory() as session:
                await risk_settings(session, self.owner, update='high', expected='medium')
        async with self.factory() as session:
            fund, held = await session.get(PaperFundRun, before.run.id), await session.get(PaperOrder, opened.id)
            self.assertEqual(fund.halt_reason, 'Test halt')
            self.assertEqual(fund.status, 'halted')
            self.assertEqual(fund.cash_balance, before.run.cash_balance)
            self.assertEqual(held.stop_price, opened.stop_price)

    async def test_competing_profile_update_detects_stale_selection(self):
        from app.services.paper_fund.settings import risk_settings
        from fastapi import HTTPException
        async with self.factory() as session:
            await get_or_create_default_portfolio(session, self.user)
            await session.commit()
        async def save(profile):
            async with self.factory() as session:
                try:
                    return await risk_settings(session, self.owner, update=profile, expected='medium')
                except HTTPException as error:
                    await session.rollback()
                    return error.status_code
        with patch('app.services.administration.system_log.publish_event', new=AsyncMock()):
            results = await asyncio.gather(save('low'), save('high'))
        self.assertEqual(sum(result == 409 for result in results), 1)

    async def test_missing_history_cannot_queue_or_fill(self):
        from sqlalchemy import delete
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle()
        self.assertTrue(any(o.status == 'pending' for o in queued.orders))
        async with self.factory() as session:
            await session.execute(delete(MarketPriceBar).where(MarketPriceBar.instrument_id == instrument_id))
            await session.commit()
        await self.quote(instrument_id, '100', NOW+timedelta(seconds=30))
        blocked = await self.call_cycle(NOW+timedelta(seconds=30))
        self.assertFalse(any(o.status in {'pending','open'} for o in blocked.orders))
        self.assertEqual(blocked.run.cash_balance, D('10000'))
        self.assertTrue(any('history' in reason for reason in blocked.blockers))

    async def test_risk_settings_api_validates_and_persists_selection(self):
        async def dependency_session():
            async with self.factory() as session:
                yield session
        app.dependency_overrides[get_session] = dependency_session
        app.dependency_overrides[require_capital_user] = lambda: self.user
        with patch('app.services.administration.system_log.publish_event', new=AsyncMock()):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
                response = await client.get('/api/paper-fund/risk-settings')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['profile'], 'medium')
                invalid = await client.post('/api/paper-fund/risk-settings', json={'profile':'extreme', 'expected_profile':'medium'})
                self.assertEqual(invalid.status_code, 422)
                changed = await client.post('/api/paper-fund/risk-settings', json={'profile':'low','expected_profile':'medium'})
                self.assertEqual(changed.status_code, 200)
                reread = await client.get('/api/paper-fund/risk-settings')
                self.assertEqual(reread.json()['profile'], 'low')
                self.assertEqual(reread.json()['options']['low']['max_position_pct'], 3)
                stale = await client.post('/api/paper-fund/risk-settings', json={'profile':'high','expected_profile':'medium'})
                self.assertEqual(stale.status_code, 409)

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

    async def test_automatic_fills_use_the_capital_ledger_and_journal(self):
        from app.services.portfolio.operating_core import get_dashboard, get_trade_journal
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            initial = await start_run(session, self.owner, PaperStart(), now=NOW)
            self.assertEqual(initial.capital.cash_balance, D("10000"))
        await self.call_cycle()
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        filled = await self.call_cycle(at)
        async with self.factory() as session:
            dashboard = await get_dashboard(session, self.user)
            self.assertEqual(dashboard.cash_balance, filled.run.cash_balance)
            self.assertEqual(dashboard.nav, filled.run.equity)
            self.assertEqual(dashboard.trade_count, 1)
            self.assertEqual(dashboard.open_position_count, 1)
            self.assertEqual(dashboard.positions[0].quantity, 9)
            self.assertEqual(dashboard.recent_trades[0].broker_reference, "automatic_paper")
            entry = next(entry for entry in dashboard.recent_cash_entries if entry.entry_type == "trade_buy")
            self.assertEqual(entry.amount, D("-901.36"))
        at += timedelta(seconds=30)
        await self.quote(instrument_id, "107", at)
        closed = await self.call_cycle(at)
        async with self.factory() as session:
            dashboard = await get_dashboard(session, self.user)
            self.assertEqual(dashboard.cash_balance, closed.run.cash_balance)
            self.assertEqual(dashboard.open_position_count, 0)
            self.assertEqual(dashboard.trade_count, 2)
            self.assertEqual(closed.run.total_pnl, closed.run.realized_pnl)
            self.assertEqual(closed.run.unrealized_pnl, 0)

    async def test_manual_mode_stops_exits_and_resumes_without_new_money(self):
        from app.services.paper_fund.engine import set_trading_mode
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            initial = await start_run(session, self.owner, PaperStart(), now=NOW)
        await self.call_cycle()
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        filled = await self.call_cycle(at)
        async with self.factory() as session:
            manual = await set_trading_mode(session, self.owner, "manual")
            self.assertEqual(manual.trading_mode, "manual")
        at += timedelta(seconds=30)
        await self.quote(instrument_id, "95", at)
        stopped = await self.call_cycle(at)
        self.assertEqual(stopped.orders[0].status, "open")
        self.assertEqual(stopped.run.cash_balance, filled.run.cash_balance)
        self.assertEqual(stopped.capital.trade_count, 1)
        async with self.factory() as session:
            resumed = await set_trading_mode(session, self.owner, "automatic")
            self.assertEqual(resumed.run.id, initial.run.id)
            self.assertEqual(resumed.run.cash_balance, filled.run.cash_balance)
        closed = await self.call_cycle(at)
        self.assertEqual(closed.orders[0].status, "closed")
        self.assertEqual(closed.capital.trade_count, 2)

    async def test_enabling_automatic_uses_available_capital_not_a_new_ten_thousand(self):
        from app.services.paper_fund.engine import set_trading_mode
        async with self.factory() as session:
            portfolio = await get_or_create_default_portfolio(session, self.user)
            await create_cash_withdrawal(session, CashWithdrawalCreate(amount=D("7000"), currency="USD", platform="test"), self.user)
        async with self.factory() as session:
            initial = await start_run(session, self.owner, PaperStart(), now=NOW)
            self.assertEqual(initial.run.starting_cash, D("3000"))
            self.assertEqual(initial.run.cash_balance, D("3000"))
            self.assertEqual(initial.capital.cash_balance, D("3000"))
            await set_trading_mode(session, self.owner, "manual")
            resumed = await set_trading_mode(session, self.owner, "automatic")
            self.assertEqual(resumed.run.id, initial.run.id)
            self.assertEqual(resumed.run.cash_balance, D("3000"))
            count = await session.scalar(select(func.count()).select_from(CashLedgerEntry).where(CashLedgerEntry.portfolio_id == portfolio.id))
            self.assertEqual(count, 2)

    async def test_pending_automatic_orders_reserve_capital_against_withdrawals(self):
        from app.services.paper_fund.engine import set_trading_mode
        await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle()
        self.assertGreater(queued.run.reserved_cash, 0)
        async with self.factory() as session:
            with self.assertRaises(CapitalValidationError):
                await create_cash_withdrawal(session, CashWithdrawalCreate(amount=D("9500"), currency="USD", platform="test"), self.user)
            await session.rollback()
            manual = await set_trading_mode(session, self.owner, "manual")
            self.assertEqual(manual.orders[0].status, "cancelled")
            self.assertEqual(manual.run.reserved_cash, 0)
            await create_cash_withdrawal(session, CashWithdrawalCreate(amount=D("9500"), currency="USD", platform="test"), self.user)
        async with self.factory() as session:
            state = await overview(session, self.owner)
            self.assertEqual(state.capital.cash_balance, D("500"))
            self.assertEqual(state.run.cash_balance, D("500"))

    async def test_automatic_sizing_respects_capitals_tighter_position_limit(self):
        from app.models import RiskLimit
        await self.seed_signal()
        async with self.factory() as session:
            portfolio = await get_or_create_default_portfolio(session, self.user)
            limit = await session.scalar(select(RiskLimit).where(RiskLimit.portfolio_id == portfolio.id,
                RiskLimit.limit_type == "max_single_equity_position_pct"))
            limit.threshold_value = D("5")
            await session.commit()
            await start_run(session, self.owner, PaperStart(), now=NOW)
        state = await self.call_cycle()
        self.assertEqual(state.orders[0].quantity, 4)
        self.assertEqual(state.policy["max_position_pct"], 5)
        self.assertLessEqual(state.run.reserved_cash, D("500"))

    async def test_legacy_run_attaches_fills_once_without_depositing_capital(self):
        from tests.unit.test_paper_fund import make_order, make_quote, make_run
        from app.services.paper_fund.engine import process_orders
        instrument_id, _ = await self.seed_signal()
        legacy = make_run(owner_user_id=self.owner, blockers=[])
        order = make_order(run_id=legacy.id, instrument_id=instrument_id, thesis="Legacy automatic entry", evidence={})
        process_orders(legacy, [order], {instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        async with self.factory() as session:
            session.add(legacy)
            await session.flush()
            session.add(order)
            await session.commit()
        async with self.factory() as session:
            attached = await start_run(session, self.owner, PaperStart(), now=NOW)
            self.assertEqual(attached.run.id, legacy.id)
            self.assertEqual(attached.capital.cash_balance, D("9098.64"))
            self.assertEqual(attached.capital.trade_count, 1)
            replay = await start_run(session, self.owner, PaperStart(), now=NOW)
            self.assertEqual(replay.capital.cash_balance, D("9098.64"))
            self.assertEqual(replay.capital.trade_count, 1)
            count = await session.scalar(select(func.count()).select_from(CashLedgerEntry).where(
                CashLedgerEntry.portfolio_id == attached.capital.portfolio.id, CashLedgerEntry.entry_type == "initial_capital"))
            self.assertEqual(count, 1)

    async def test_manual_partial_sale_cannot_leave_an_oversized_automatic_exit(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from app.api.schemas.operating_core import InstrumentCreate, ManualTradeCreate
        from app.services.paper_fund.engine import set_trading_mode
        from app.services.portfolio.operating_core import create_manual_trade
        instrument_id, _ = await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        await self.call_cycle()
        at = NOW + timedelta(seconds=30)
        await self.quote(instrument_id, "100", at)
        await self.call_cycle(at)
        async with self.factory() as session:
            manual = await set_trading_mode(session, self.owner, "manual")
            instrument = await session.get(Instrument, instrument_id)
            payload = ManualTradeCreate(instrument=InstrumentCreate(ticker=instrument.ticker, name=instrument.name,
                asset_class="equity", currency="USD", sector="Technology"), side="sell", quantity=4,
                price=102, fees=0, trade_date=at + timedelta(seconds=1))
            with patch("app.services.portfolio.operating_core._ensure_trade_risk_approval",
                       AsyncMock(return_value=SimpleNamespace(id=None, decision="approve"))):
                await create_manual_trade(session, payload, self.user)
            resumed = await set_trading_mode(session, self.owner, "automatic")
            self.assertEqual(resumed.orders[0].status, "cancelled")
            self.assertEqual(resumed.capital.positions[0].quantity, 5)
        at += timedelta(seconds=30)
        await self.quote(instrument_id, "90", at)
        state = await self.call_cycle(at)
        self.assertEqual(state.capital.positions[0].quantity, 5)
        self.assertEqual(state.capital.trade_count, 2)

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
            clock = type('Clock', (datetime,), {'now':classmethod(lambda cls, tz=None: NOW)})
            with patch('app.services.paper_fund.engine.datetime', clock):
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
            self.assertEqual(missing.status_code, 200)
            self.assertEqual(missing.json()["trading_mode"], "manual")

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

    async def test_unquoted_radar_name_is_reported_instead_of_silently_disappearing(self):
        await self.seed_signal()
        async with self.factory() as session:
            radar = await session.scalar(select(RadarRun).order_by(RadarRun.started_at.desc()).limit(1))
            session.add(RadarSnapshot(run_id=radar.id, ticker='NOQUOTE', name='Unquoted discovery',
                jurisdiction='US', currency='USD', asset_class='equity', source='fmp',
                price=D('20'), change_pct=D('8'), as_of=NOW, source_as_of=NOW,
                radar_priority='P0', priority_score=D('99'), evidence={}))
            await session.commit()
            await start_run(session, self.owner, PaperStart(), now=NOW)
        result = await self.call_cycle()
        self.assertTrue(any('NOQUOTE: No verified instrument' in blocker for blocker in result.blockers))
        self.assertFalse(any(order.ticker == 'NOQUOTE' for order in result.orders))

    async def test_worker_refreshes_order_quotes_and_cycles_without_rendering_dashboard(self):
        from app.services.paper_fund.quotes import refresh_order_quotes
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        await self.seed_signal()
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        async with self.factory() as session:
            with patch('app.services.paper_fund.engine.overview', AsyncMock(side_effect=AssertionError('Worker should not render UI'))):
                self.assertIsNone(await cycle(session, self.owner, now=NOW, include_overview=False))
        async with self.factory() as session:
            with patch('app.services.paper_fund.quotes.ingest_quotes', AsyncMock(return_value=SimpleNamespace(success_count=1))) as ingest:
                self.assertEqual(await refresh_order_quotes(session, now=NOW), 1)
                self.assertEqual(len(ingest.await_args.args[1]), 1)
            result = await overview(session, self.owner, now=NOW)
            self.assertEqual(len(result.orders), 1)
            self.assertEqual(result.orders[0].status, 'pending')
            self.assertEqual(result.run.last_cycle_at, NOW)

    async def test_reference_price_entry_and_exit_reconcile_to_capital(self):
        instrument_id, _ = await self.seed_signal()
        async def reference(price, at):
            async with self.factory() as session:
                quote = await session.scalar(select(InstrumentQuote).where(InstrumentQuote.instrument_id == instrument_id))
                quote.source = 'tiingo_reference'
                quote.price = D(price)
                quote.as_of = at
                quote.raw_payload = {'ticker':'TEST', 'timestamp':at.isoformat(), 'tngoLast':price}
                await session.commit()
        await reference('100', NOW)
        async with self.factory() as session:
            await start_run(session, self.owner, PaperStart(), now=NOW)
        queued = await self.call_cycle(NOW)
        self.assertEqual(queued.orders[0].status, 'pending')
        await reference('100', NOW + timedelta(seconds=30))
        opened = await self.call_cycle(NOW + timedelta(seconds=30))
        self.assertEqual(opened.orders[0].status, 'open')
        self.assertLess(opened.capital.cash_balance, D('10000'))
        await reference('108', NOW + timedelta(seconds=60))
        closed = await self.call_cycle(NOW + timedelta(seconds=60))
        self.assertEqual(closed.orders[0].status, 'closed')
        self.assertEqual(closed.orders[0].exit_reason, 'take_profit')
        self.assertEqual(closed.run.cash_balance, closed.capital.cash_balance)
        self.assertGreater(closed.run.cash_balance, D('10000'))
        self.assertEqual(closed.capital.open_position_count, 0)
