from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch
import httpx
from app.services.market_data.quote_provider import _fetch_tiingo_iex, _clear_provider_backoff
from app.services.market_radar.execution import quote_rejection

NOW = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)

class ReferenceFeedTests(IsolatedAsyncioTestCase):
    async def parse(self, payload):
        _clear_provider_backoff()
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.get.return_value = httpx.Response(200, request=httpx.Request('GET', 'https://example.test/iex'), json=[payload])
        with patch('app.services.market_data.quote_provider.httpx.AsyncClient', return_value=client):
            return await _fetch_tiingo_iex(['TEST'])

    async def test_reference_feed_is_distinct_and_uses_provider_refresh_time(self):
        payload = {'ticker':'TEST', 'last':None, 'lastSaleTimestamp':None,
                   'tngoLast':105, 'timestamp':NOW.isoformat(), 'prevClose':100, 'volume':1200}
        quotes, available = await self.parse(payload)
        self.assertTrue(available)
        result = quotes['TEST']
        self.assertEqual(result.source, 'tiingo_reference')
        self.assertEqual(result.as_of, NOW)
        self.assertEqual(result.change_pct, Decimal('5'))
        quote = SimpleNamespace(**result.__dict__, is_stale=False)
        self.assertIsNone(quote_rejection(quote, NOW))
        self.assertIsNotNone(quote_rejection(quote, NOW + timedelta(seconds=121)))
        self.assertIsNotNone(quote_rejection(quote, NOW - timedelta(seconds=1)))
        quote.price = Decimal('106')
        self.assertIn('does not match', quote_rejection(quote, NOW))

    async def test_trade_price_uses_trade_timestamp_not_newer_reference_timestamp(self):
        quotes, _ = await self.parse({'ticker':'TEST', 'last':100, 'lastSaleTimestamp':NOW.isoformat(),
            'tngoLast':105, 'timestamp':(NOW+timedelta(seconds=10)).isoformat()})
        result = quotes['TEST']
        self.assertEqual((result.source, result.price, result.as_of), ('tiingo', Decimal('100'), NOW))

    async def test_mid_without_documented_reference_is_not_accepted(self):
        quotes, available = await self.parse({'ticker':'TEST', 'mid':105, 'timestamp':NOW.isoformat()})
        self.assertFalse(available)
        self.assertEqual(quotes, {})
