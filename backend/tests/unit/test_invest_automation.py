"""Invest automatic plans stay on the Invest book and wait for a later quote."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import app.main  # noqa: F401  # application import order, then the broker
from app.services.brokerage.paper import _balances, concentration_exceeds
from app.services.invest.automation import Book, advance
from app.services.market_data.quote_cache import get_or_fetch_quote_price
from app.services.paper_fund.engine import fee

NOW = datetime(2026, 10, 19, 15, 0, 30, tzinfo=timezone.utc)
SUBMITTED = datetime(2026, 10, 19, 14, 59, tzinfo=timezone.utc)
QUOTED = datetime(2026, 10, 19, 15, 0, tzinfo=timezone.utc)


def quote(price, at=QUOTED):
    return SimpleNamespace(
        price=Decimal(price), is_stale=False, currency="USD", source="tiingo", as_of=at,
        previous_close=Decimal("90"), change_pct=Decimal("5"),
        raw_payload={"lastSaleTimestamp": at.isoformat()},
    )


def book(**kwargs):
    values = dict(
        cash=Decimal("10000"), reserved_cash=Decimal("100.16"), realized_pnl=Decimal("0"),
        high_water_equity=Decimal("10000"), max_drawdown_pct=Decimal("0"),
        trading_mode="automatic", automation_status="running", halt_reason=None, marks_reliable=True,
    )
    values.update(kwargs)
    return Book(**values)


def plan(**kwargs):
    values = dict(
        id=uuid4(), instrument_id=uuid4(), ticker="TEST", sector="Technology", asset_class="equity",
        status="pending", quantity=Decimal("1"), limit_price=Decimal("100.10"),
        stop_price=Decimal("97.09"), target_price=Decimal("106.11"),
        reserved_cash=Decimal("100.16"), submitted_at=SUBMITTED,
        expires_at=SUBMITTED + timedelta(minutes=20), evidence={},
        entry_price=None, entry_fee=Decimal("0"), exit_price=None, exit_fee=Decimal("0"),
        realized_pnl=Decimal("0"), opened_at=None, closed_at=None, entry_quote_at=None,
        mark_price=None, mark_as_of=None, exit_reason=None, signal_id=None,
        available_quantity=None, name="Test",
    )
    values.update(kwargs)
    return SimpleNamespace(**values)


class InvestPlanTests(TestCase):
    def test_fill_uses_a_later_quote_and_releases_the_reservation(self):
        entry = plan()
        state = book()
        advance(state, [entry], {entry.instrument_id: quote("100")}, [], NOW)
        self.assertEqual(entry.status, "open")
        self.assertEqual(entry.entry_price, Decimal("100.10"))
        self.assertEqual(entry.entry_fee, fee(Decimal("100.10"), {"fee_bps": 5}))
        self.assertEqual(state.cash, Decimal("9899.84"))
        self.assertEqual(state.reserved_cash, Decimal("0.00"))

    def test_the_quote_that_created_the_order_cannot_fill_it(self):
        entry = plan()
        state = book()
        advance(state, [entry], {entry.instrument_id: quote("100", SUBMITTED)}, [], NOW)
        self.assertEqual(entry.status, "pending")
        self.assertEqual(state.cash, Decimal("10000"))
        self.assertEqual(state.reserved_cash, Decimal("100.16"))

    def test_a_quote_through_the_limit_waits(self):
        entry = plan()
        state = book()
        advance(state, [entry], {entry.instrument_id: quote("102")}, [], NOW)
        self.assertEqual(entry.status, "pending")

    def test_expiry_releases_reserved_cash_once(self):
        entry = plan(expires_at=SUBMITTED)
        state = book()
        advance(state, [entry], {}, [], NOW)
        advance(state, [entry], {}, [], NOW)
        self.assertEqual(entry.status, "expired")
        self.assertEqual(state.reserved_cash, Decimal("0.00"))
        self.assertEqual(state.cash, Decimal("10000"))

    def test_manual_mode_keeps_stop_exits_and_cancels_unfilled_buys(self):
        held = plan(
            status="open", reserved_cash=Decimal("0"), entry_price=Decimal("100"),
            entry_fee=Decimal("0.05"), entry_quote_at=SUBMITTED, opened_at=SUBMITTED,
        )
        waiting = plan(instrument_id=held.instrument_id)
        state = book(trading_mode="manual", reserved_cash=Decimal("100.16"), automation_status="paused")
        advance(state, [held, waiting], {held.instrument_id: quote("90")}, [], NOW)
        self.assertEqual(waiting.status, "cancelled")
        self.assertEqual(held.status, "closed")
        self.assertEqual(held.exit_reason, "stop_loss")
        self.assertGreater(state.cash, Decimal("10000"))

    def test_a_latched_halt_still_sells_in_manual_mode(self):
        held = plan(
            status="open", reserved_cash=Decimal("0"), entry_price=Decimal("100"),
            entry_fee=Decimal("0.05"), entry_quote_at=SUBMITTED, limit_price=Decimal("100.10"),
            stop_price=Decimal("90"), target_price=Decimal("120"),
        )
        state = book(trading_mode="manual", automation_status="halted", halt_reason="drawdown", reserved_cash=Decimal("0"))
        advance(state, [held], {held.instrument_id: quote("100")}, [], NOW)
        self.assertEqual(held.status, "closed")
        self.assertEqual(held.exit_reason, "drawdown_halt")

    def test_a_manual_sale_of_the_whole_position_closes_the_plan_without_cash(self):
        held = plan(
            status="open", reserved_cash=Decimal("0"), entry_price=Decimal("100"),
            entry_fee=Decimal("0.05"), entry_quote_at=SUBMITTED, available_quantity=Decimal("0"),
        )
        state = book(reserved_cash=Decimal("0"))
        advance(state, [held], {held.instrument_id: quote("90")}, [], NOW)
        self.assertEqual(held.status, "closed")
        self.assertIsNone(held.exit_price)
        self.assertEqual(state.cash, Decimal("10000"))

    def test_manual_mode_does_not_latch_a_new_halt(self):
        state = book(trading_mode="manual", cash=Decimal("9000"), reserved_cash=Decimal("0"), automation_status="paused")
        blockers = advance(state, [], {}, [], NOW)
        self.assertEqual(state.automation_status, "paused")
        self.assertIsNone(state.halt_reason)
        self.assertTrue(any("would halt" in item for item in blockers))

    def test_automatic_mode_latches_drawdown_and_cancels_the_buy(self):
        entry = plan()
        state = book(cash=Decimal("9000"))
        advance(state, [entry], {}, [], NOW)
        self.assertEqual(state.automation_status, "halted")
        self.assertEqual(entry.status, "cancelled")
        self.assertEqual(state.reserved_cash, Decimal("0.00"))


class InvestCashTests(TestCase):
    def test_concentration_uses_equity_without_adding_the_purchase(self):
        self.assertTrue(concentration_exceeds(Decimal("0"), Decimal("3000"), Decimal("10000"), Decimal("0.25")))
        self.assertFalse(concentration_exceeds(Decimal("0"), Decimal("2000"), Decimal("10000"), Decimal("0.25")))
        self.assertTrue(concentration_exceeds(Decimal("1000"), Decimal("2000"), Decimal("10000"), Decimal("0.25")))

    def test_buying_power_excludes_reserved_cash(self):
        balances = _balances(SimpleNamespace(cash_balance=Decimal("10000"), reserved_cash=Decimal("400"), base_currency="USD"))
        self.assertEqual(balances.buying_power, Decimal("9600.00"))
        self.assertEqual(balances.pending, Decimal("400.00"))
        self.assertEqual(balances.cash, Decimal("10000.00"))


class InvestQuoteTests(IsolatedAsyncioTestCase):
    async def test_a_different_symbol_is_not_a_fill_price(self):
        other = SimpleNamespace(ticker="OTHER", price=Decimal("999"))
        with patch("app.services.market_data.quote_cache.get_cached_quote_price", AsyncMock(return_value=None)), \
             patch("app.services.market_data.quote_cache.fetch_quotes", AsyncMock(return_value={"OTHER": other})):
            price = await get_or_fetch_quote_price(SimpleNamespace(), "TEST")
        self.assertIsNone(price)
