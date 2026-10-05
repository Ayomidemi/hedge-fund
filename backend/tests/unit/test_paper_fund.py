from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest import TestCase
from uuid import uuid4

from pydantic import ValidationError

from app.api.schemas.paper_fund import PaperStart
from app.models import InstrumentQuote, PaperFundRun, PaperOrder, RadarSnapshot
from app.services.market_radar.execution import execution_rejection, quote_rejection
from app.services.paper_fund.calendar import market_blocker
from app.services.paper_fund.engine import POLICY, accounting, process_orders, reservation, size_order

D = Decimal
NOW = datetime(2026, 10, 2, 15, tzinfo=timezone.utc)


def make_run(**changes):
    values = dict(id=uuid4(), owner_user_id="paper-test", status="running", starting_cash=D("10000"),
                  cash_balance=D("10000"), high_water_equity=D("10000"), max_drawdown_pct=D("0"),
                  started_at=NOW, ends_at=NOW + timedelta(days=7), policy=dict(POLICY), halt_reason=None)
    values.update(changes)
    return PaperFundRun(**values)


def make_order(**changes):
    values = dict(id=uuid4(), run_id=uuid4(), instrument_id=uuid4(), ticker="ACME", name="Acme", sector="Technology",
                  status="pending", quantity=9, limit_price=D("100.10"), stop_price=D("97.09"), target_price=D("106.11"),
                  entry_price=None, exit_price=None, mark_price=None, entry_fee=D("0"), exit_fee=D("0"), realized_pnl=D("0"),
                  submitted_at=NOW, expires_at=NOW + timedelta(minutes=15), entry_quote_at=None, mark_as_of=None)
    values.update(changes)
    return PaperOrder(**values)


def make_quote(order, price="100", at=None, **changes):
    at = at or NOW + timedelta(seconds=30)
    values = dict(instrument_id=order.instrument_id, price=D(price), currency="USD", source="fmp", as_of=at,
                  is_stale=False, raw_payload={"timestamp": int(at.timestamp())})
    values.update(changes)
    return InstrumentQuote(**values)


def make_signal(**changes):
    values = dict(ticker="ACME", jurisdiction="US", currency="USD", asset_class="equity", carried_forward=False,
                  stale_reason=None, as_of=NOW, source_as_of=NOW, radar_priority="P1", change_pct=D("5"),
                  price=D("100"), volume_ratio=D("2.5"), evidence={"avg_dollar_volume": "10000000"})
    values.update(changes)
    return RadarSnapshot(**values)


class PaperFundTests(TestCase):
    def test_trial_baseline_is_fixed_and_finite(self):
        for value in ("NaN", "Infinity", "0", "100000"):
            with self.assertRaises(ValidationError):
                PaperStart(starting_cash=value)
        self.assertEqual(PaperStart().starting_cash, D("10000"))

    def test_sizing_includes_fees_and_rounds_to_affordable_whole_shares(self):
        run = make_run()
        qty, limit, stop, target = size_order(run, [], D("100"), "Technology")
        self.assertEqual(qty, 9)
        self.assertLess(stop, limit)
        self.assertGreater(target, limit)
        order = make_order(quantity=qty, limit_price=limit)
        self.assertLessEqual(reservation(order, run.policy), D("1000"))
        self.assertEqual(size_order(run, [], D("2000"), "Technology")[0], 0)

    def test_sector_and_position_capacity_include_pending_orders(self):
        run = make_run()
        orders = [make_order(quantity=9), make_order(quantity=9)]
        self.assertEqual(size_order(run, orders, D("100"), "Technology")[0], 1)
        orders = [make_order(sector=str(index)) for index in range(5)]
        self.assertEqual(size_order(run, orders, D("100"), "Other")[0], 0)

    def test_reservation_is_not_a_cash_expense(self):
        run, order = make_run(), make_order()
        state = accounting(run, [order])
        self.assertEqual(state["equity"], D("10000"))
        self.assertEqual(state["reserved_cash"], D("901.36"))
        self.assertEqual(state["available_cash"], D("9098.64"))
        self.assertEqual(state["total_pnl"], D("0"))

    def test_initial_quote_never_fills_its_own_order(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order, at=NOW)}, NOW)
        self.assertEqual(order.status, "pending")
        self.assertEqual(run.cash_balance, D("10000"))

    def test_buy_limit_waits_for_a_price_it_can_fill_after_slippage(self):
        run, order = make_run(), make_order()
        now = NOW + timedelta(seconds=30)
        process_orders(run, [order], {order.instrument_id: make_quote(order, "101")}, now)
        self.assertEqual(order.status, "pending")
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, now)
        self.assertEqual(order.status, "open")
        self.assertEqual(order.entry_price, D("100.10"))
        self.assertEqual(run.cash_balance, D("9098.64"))
        self.assertEqual(accounting(run, [order])["total_pnl"], D("-1.36"))
        # Retrying a cycle with identical quotes cannot debit cash twice.
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, now)
        self.assertEqual(run.cash_balance, D("9098.64"))

    def test_stop_gaps_fill_at_observed_price_and_reconcile_with_cash(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        later = NOW + timedelta(minutes=1)
        process_orders(run, [order], {order.instrument_id: make_quote(order, "90", at=later)}, later)
        self.assertEqual(order.status, "closed")
        self.assertEqual(order.exit_price, D("89.91"))
        self.assertEqual(order.exit_reason, "stop_loss")
        self.assertEqual(order.realized_pnl, D("-92.58"))
        state = accounting(run, [order])
        self.assertEqual(state["realized_pnl"], state["total_pnl"])
        self.assertEqual(run.cash_balance, D("9907.42"))

    def test_profit_target_requires_executable_price_after_slippage(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        later = NOW + timedelta(minutes=1)
        process_orders(run, [order], {order.instrument_id: make_quote(order, "106.11", at=later)}, later)
        self.assertEqual(order.status, "open")
        process_orders(run, [order], {order.instrument_id: make_quote(order, "107", at=later)}, later)
        self.assertEqual(order.status, "closed")
        self.assertEqual(order.exit_reason, "take_profit")
        self.assertGreater(order.realized_pnl, 0)

    def test_paused_run_continues_protective_exits(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        run.status = "paused"
        later = NOW + timedelta(minutes=1)
        process_orders(run, [order], {order.instrument_id: make_quote(order, "95", at=later)}, later)
        self.assertEqual(order.status, "closed")

    def test_stale_future_or_unverifiable_quotes_never_fill(self):
        for quote_at, raw, stale in ((NOW - timedelta(minutes=5), None, False),
                                     (NOW + timedelta(minutes=5), None, False),
                                     (NOW + timedelta(seconds=30), {}, False),
                                     (NOW + timedelta(seconds=30), None, True)):
            run, order = make_run(), make_order()
            quote = make_quote(order, at=quote_at, is_stale=stale)
            if raw is not None:
                quote.raw_payload = raw
            process_orders(run, [order], {order.instrument_id: quote}, NOW + timedelta(seconds=30))
            self.assertEqual(order.status, "pending")
            self.assertEqual(run.cash_balance, D("10000"))

    def test_expiration_and_gap_before_entry_release_reserved_cash(self):
        for price, at, expected in (("100", NOW + timedelta(hours=1), "expired"),
                                    ("90", NOW + timedelta(seconds=30), "cancelled")):
            run, order = make_run(), make_order()
            process_orders(run, [order], {order.instrument_id: make_quote(order, price, at=at)}, at)
            self.assertEqual(order.status, expected)
            self.assertEqual(accounting(run, [order])["reserved_cash"], 0)

    def test_drawdown_halt_cancels_pending_and_liquidates_without_reopening(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        pending = make_order(ticker="NEXT")
        run.high_water_equity = D("11000")
        later = NOW + timedelta(minutes=1)
        process_orders(run, [order, pending], {order.instrument_id: make_quote(order, "100", at=later)}, later)
        self.assertEqual(run.status, "halted")
        self.assertEqual(pending.status, "cancelled")
        self.assertEqual(order.exit_reason, "drawdown_halt")
        self.assertTrue(run.halt_reason)

    def test_week_end_waits_for_valid_exit_then_freezes_final_result(self):
        run, order = make_run(), make_order()
        process_orders(run, [order], {order.instrument_id: make_quote(order)}, NOW + timedelta(seconds=30))
        end = run.ends_at
        process_orders(run, [order], {}, end)
        self.assertEqual(run.status, "liquidating")
        self.assertEqual(order.status, "open")
        process_orders(run, [order], {order.instrument_id: make_quote(order, "103", at=end)}, end)
        self.assertEqual(run.status, "completed")
        self.assertEqual(order.exit_reason, "review_period_ended")
        final_cash = run.cash_balance
        process_orders(run, [order], {order.instrument_id: make_quote(order, "200", at=end)}, end)
        self.assertEqual(run.cash_balance, final_cash)

    def test_closed_market_does_not_fill_even_with_fresh_quote(self):
        run, order = make_run(), make_order(expires_at=NOW + timedelta(days=3))
        saturday = NOW + timedelta(days=1)
        process_orders(run, [order], {order.instrument_id: make_quote(order, at=saturday)}, saturday)
        self.assertEqual(order.status, "pending")


class ExecutionEligibilityTests(TestCase):
    def test_complete_signal_is_eligible_but_not_negative_or_illiquid(self):
        quote = make_quote(make_order(), at=NOW)
        self.assertIsNone(execution_rejection(make_signal(), quote, NOW))
        for signal in (make_signal(change_pct=D("-5")), make_signal(volume_ratio=None),
                       make_signal(evidence={}), make_signal(currency="NGN"),
                       make_signal(carried_forward=True), make_signal(source_as_of=NOW - timedelta(hours=1))):
            self.assertIsNotNone(execution_rejection(signal, quote, NOW))

    def test_stream_requires_original_provider_time(self):
        order = make_order()
        quote = make_quote(order, source="tiingo_stream", at=NOW,
                           raw_payload={"provider_timestamp": NOW.isoformat()})
        self.assertIsNotNone(quote_rejection(quote, NOW))
        quote.raw_payload = {"message": {"service": "iex", "messageType": "A", "data": [NOW.isoformat(), "ACME", 100]}}
        self.assertIsNone(quote_rejection(quote, NOW))


class PaperCalendarTests(TestCase):
    def test_dst_holiday_early_close_and_unknown_calendar(self):
        for at in ("2026-01-05T14:00:00+00:00", "2026-07-03T15:00:00+00:00",
                   "2026-11-27T18:00:00+00:00", "2026-10-02T20:00:00+00:00", "2029-01-02T16:00:00+00:00"):
            self.assertIsNotNone(market_blocker(datetime.fromisoformat(at)), at)
        for at in ("2026-01-05T14:30:00+00:00", "2026-10-02T13:30:00+00:00", "2026-11-27T17:59:00+00:00"):
            self.assertIsNone(market_blocker(datetime.fromisoformat(at)), at)
