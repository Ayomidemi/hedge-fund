from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest import TestCase, IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from app.services.paper_fund.history import _previous_session, _select_batch, _supported

NOW = datetime(2026, 10, 14, 15, tzinfo=timezone.utc)


class HistoryPreparationTests(TestCase):
    def test_holding_has_one_reserved_slot_and_discoveries_get_the_rest(self):
        rows = [SimpleNamespace(ticker=f'NEW{i}', last_attempt_at=None) for i in range(5)]
        rows += [SimpleNamespace(ticker=f'HELD{i}', last_attempt_at=None) for i in range(5)]
        selected = _select_batch(rows, {f'HELD{i}' for i in range(5)})
        self.assertEqual(len(selected), 4)
        self.assertEqual(sum(row.ticker.startswith('HELD') for row in selected), 1)
        self.assertEqual([row.ticker for row in selected[1:]], ['NEW0', 'NEW1', 'NEW2'])

    def test_persistent_oldest_attempt_order_survives_queue_size_changes(self):
        old = SimpleNamespace(ticker='OLD', last_attempt_at=NOW-timedelta(days=1))
        recent = SimpleNamespace(ticker='RECENT', last_attempt_at=NOW)
        new = SimpleNamespace(ticker='NEW', last_attempt_at=None)
        self.assertEqual([row.ticker for row in _select_batch([recent, old, new], set())],
                         ['NEW', 'OLD', 'RECENT'])

    def test_previous_session_accounts_for_weekends_and_holidays(self):
        self.assertEqual(_previous_session(datetime(2026, 7, 6, 15, tzinfo=timezone.utc)).isoformat(), '2026-07-02')
        self.assertEqual(_previous_session(NOW).isoformat(), '2026-10-13')

    def test_history_eligibility_is_usd_equities_and_etfs(self):
        for ticker, currency, asset, expected in (
            ('NEW', 'USD', 'equity', True), ('ETF', 'USD', 'etf', True),
            ('BOND', 'USD', 'bond', False), ('GTCO.NG', 'USD', 'equity', False),
            ('NG', 'NGN', 'equity', False),
        ):
            self.assertEqual(_supported(SimpleNamespace(ticker=ticker, currency=currency, asset_class=asset)), expected)


class HistoryWorkerDeadlineTests(IsolatedAsyncioTestCase):
    async def test_total_deadline_releases_session_lock_and_engine(self):
        from app.workers.tasks.paper_fund import _refresh_history
        engine = SimpleNamespace(dispose=AsyncMock())
        session_context = AsyncMock()
        lock_context = AsyncMock()
        lock_context.__aenter__.return_value = True
        async def stalled(*args, **kwargs):
            await asyncio.sleep(10)
        with patch('app.workers.tasks.paper_fund.create_async_engine', return_value=engine), \
             patch('app.workers.tasks.paper_fund.async_sessionmaker', return_value=MagicMock(return_value=session_context)), \
             patch('app.workers.tasks.paper_fund.hold_job_lock', return_value=lock_context), \
             patch('app.workers.tasks.paper_fund.HISTORY_JOB_TIMEOUT_SECONDS', 0.02), \
             patch('app.services.paper_fund.history.refresh_risk_history', new=stalled):
            await asyncio.wait_for(_refresh_history(), timeout=1)
        self.assertEqual(session_context.__aenter__.await_count, session_context.__aexit__.await_count)
        self.assertGreaterEqual(session_context.__aexit__.await_count, 1)
        lock_context.__aexit__.assert_awaited_once()
        engine.dispose.assert_awaited_once()
