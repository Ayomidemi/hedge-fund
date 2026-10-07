from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.services.paper_fund.quotes import refresh_order_quotes

NOW = datetime(2026, 10, 6, 15, tzinfo=timezone.utc)


def quote(at):
    return SimpleNamespace(as_of=at, price=Decimal('100'), currency='USD', source='fmp',
                           is_stale=False, raw_payload={'timestamp': int(at.timestamp())})


class ExecutionQuoteTests(IsolatedAsyncioTestCase):
    async def test_closed_market_does_no_database_or_provider_work(self):
        self.assertEqual(await refresh_order_quotes(object(), now=NOW.replace(hour=22)), 0)

    async def test_fresh_stream_quotes_need_no_rest_request(self):
        instrument = SimpleNamespace(id=uuid4(), ticker='TEST')
        order = SimpleNamespace(status='pending', submitted_at=NOW-timedelta(seconds=30))
        session = SimpleNamespace(execute=AsyncMock(return_value=[(instrument, quote(NOW), order)]))
        with patch('app.services.paper_fund.quotes.ingest_quotes', AsyncMock()) as ingest:
            self.assertEqual(await refresh_order_quotes(session, now=NOW), 0)
            ingest.assert_not_awaited()

    async def test_pending_orders_fetch_later_observation_and_deduplicate_across_accounts(self):
        instrument = SimpleNamespace(id=uuid4(), ticker='TEST')
        order = SimpleNamespace(status='pending', submitted_at=NOW)
        row = (instrument, quote(NOW), order)
        session = SimpleNamespace(execute=AsyncMock(return_value=[row, row]), commit=AsyncMock())
        with patch('app.services.paper_fund.quotes.ingest_quotes', AsyncMock(return_value=SimpleNamespace(success_count=1))) as ingest:
            self.assertEqual(await refresh_order_quotes(session, now=NOW), 1)
            ingest.assert_awaited_once_with(session, {'TEST': [instrument.id]})
            session.commit.assert_awaited_once()

    async def test_open_positions_refresh_before_quotes_exceed_execution_age_limit(self):
        instrument = SimpleNamespace(id=uuid4(), ticker='TEST')
        order = SimpleNamespace(status='open', submitted_at=NOW-timedelta(minutes=5))
        session = SimpleNamespace(execute=AsyncMock(return_value=[(instrument, quote(NOW-timedelta(seconds=60)), order)]), commit=AsyncMock())
        with patch('app.services.paper_fund.quotes.ingest_quotes', AsyncMock(return_value=SimpleNamespace(success_count=1))) as ingest:
            await refresh_order_quotes(session, now=NOW)
            ingest.assert_awaited_once()
