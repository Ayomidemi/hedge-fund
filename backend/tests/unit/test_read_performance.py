"""Regressions for transaction-local read reuse and non-blocking authentication."""
import asyncio
import threading
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch

from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import auth
from app.db.read_cache import transaction_read_cache
from app.services.brokerage.protocol import BrokerPosition
from app.services.invest.accounts import _holdings
from app.services.invest import configuration


class MetadataCacheTests(TestCase):
    def test_sessions_and_transaction_boundaries_are_isolated(self):
        first, second = AsyncSession(), AsyncSession()
        first.sync_session.begin()
        transaction_read_cache(first)['schema'] = True
        self.assertNotIn('schema', transaction_read_cache(second))
        self.assertTrue(transaction_read_cache(first)['schema'])
        first.sync_session.rollback()
        self.assertEqual(transaction_read_cache(first), {})
        first.sync_session.begin()
        transaction_read_cache(first)['seeded'] = True
        first.sync_session.commit()
        self.assertEqual(transaction_read_cache(first), {})

    def test_savepoint_rollback_discards_metadata(self):
        session = AsyncSession()
        session.sync_session.begin()
        transaction_read_cache(session)['outer'] = True
        savepoint = session.sync_session.begin_nested()
        self.assertEqual(transaction_read_cache(session), {})
        transaction_read_cache(session)['seeded'] = True
        savepoint.rollback()
        self.assertEqual(transaction_read_cache(session), {})
        session.sync_session.rollback()


class ReadReuseTests(IsolatedAsyncioTestCase):
    async def test_broker_marks_are_reused_without_database_or_quote_requests(self):
        position = BrokerPosition(
            symbol='TEST', quantity=Decimal('2'), average_cost=Decimal('90'),
            market_value=Decimal('200'), unrealized_pnl=Decimal('20'),
            unrealized_pnl_pct=Decimal('11.1111'), instrument_name='Test',
            asset_class='equity', currency='USD', current_price=Decimal('100'),
        )
        # An object with no DB methods makes any accidental second lookup fail.
        result = await _holdings(object(), [position])
        self.assertEqual(result[0].current_price, Decimal('100'))
        self.assertEqual(result[0].market_value, Decimal('200'))
        self.assertEqual(result[0].unrealized_pnl, Decimal('20'))
        self.assertEqual(await _holdings(object(), []), [])

    async def test_configured_setting_uses_one_read_and_keeps_overrides(self):
        key = next(iter(configuration.DEFAULT_INVEST_SETTINGS))
        fallback = configuration.default_invest_setting(key)
        session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(is_active=True, payload=fallback)))
        with patch.object(configuration, '_invest_settings_table_exists', AsyncMock(return_value=True)), patch.object(configuration, 'ensure_invest_settings', AsyncMock()) as seed:
            self.assertEqual(await configuration.get_invest_setting(session, key), fallback)
            session.scalar.assert_awaited_once()
            seed.assert_not_awaited()

    async def test_inactive_setting_falls_back_without_reseeding(self):
        key = next(iter(configuration.DEFAULT_INVEST_SETTINGS))
        session = SimpleNamespace(scalar=AsyncMock(return_value=SimpleNamespace(is_active=False, payload={})))
        with patch.object(configuration, '_invest_settings_table_exists', AsyncMock(return_value=True)), patch.object(configuration, 'ensure_invest_settings', AsyncMock()) as seed:
            self.assertEqual(await configuration.get_invest_setting(session, key), configuration.default_invest_setting(key))
            seed.assert_not_awaited()

    async def test_missing_setting_still_seeds_defaults(self):
        key = next(iter(configuration.DEFAULT_INVEST_SETTINGS))
        session = SimpleNamespace(scalar=AsyncMock(return_value=None))
        with patch.object(configuration, '_invest_settings_table_exists', AsyncMock(return_value=True)), patch.object(configuration, 'ensure_invest_settings', AsyncMock(return_value=True)) as seed:
            self.assertEqual(await configuration.get_invest_setting(session, key), configuration.default_invest_setting(key))
            seed.assert_awaited_once_with(session, [key])

    async def test_token_verification_runs_off_event_loop_for_both_dependencies(self):
        loop_thread = threading.get_ident()
        def decode(_token):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return {'sub': 'test-user', 'app_metadata': {'role': 'ADMIN'}}
        credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials='test')
        with patch.object(auth, 'settings', SimpleNamespace(auth_enabled=True)), patch.object(auth, '_decode_supabase_token', decode):
            users = await asyncio.gather(auth.get_optional_user(credentials), auth.require_authenticated_user(credentials))
        self.assertEqual([user.id for user in users], ['test-user', 'test-user'])
