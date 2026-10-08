from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from types import SimpleNamespace as NS
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.services.risk.policy import profile_policy, apply_account_limits
from app.services.risk.risk_centre import (
    PortfolioRiskState, RiskPosition, compute_portfolio_market_stats,
    _var_pct, _expected_shortfall_pct, build_risk_overview_from_state, _pre_trade_decision,
    _returns_by_date, _portfolio_returns,
)
from app.services.paper_fund.engine import daily_loss_blocker, process_orders, size_order
from app.services.paper_fund.risk import entry_risk
from app.api.schemas.paper_fund import RiskProfileUpdate
from pydantic import ValidationError

NOW = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)


def history(count=253, as_of=NOW.date(), amplitude=D('0.001')):
    bars = []
    day = as_of - timedelta(days=1)
    for i in range(count):
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        close = D('100') * (1 + amplitude * (i % 2))
        bars.append(NS(bar_date=day, adjusted_close_price=close, close_price=close,
                       volume=1000000, raw_payload={}))
        day -= timedelta(days=1)
    return list(reversed(bars))


def position(ticker='TEST', value='500'):
    return RiskPosition(uuid4(), ticker, ticker, 'equity', ticker, D('5'), D('100'), D(value), D('0'))


def state(positions):
    invested = sum((p.market_value for p in positions), D('0'))
    return PortfolioRiskState(uuid4(), 'Test', NOW, NOW.date(), D('10000'), D('10000') - invested,
                               invested, positions, effective_policy=profile_policy())


def run(**changes):
    values = dict(policy=profile_policy(), portfolio_id=uuid4(), cash_balance=D('10000'),
        starting_cash=D('10000'), high_water_equity=D('10000'), max_drawdown_pct=D('0'),
        risk_state={}, status='running', ends_at=NOW+timedelta(days=7), halt_reason=None)
    values.update(changes)
    return NS(**values)


def order(**changes):
    values = dict(instrument_id=uuid4(), ticker='TEST', sector='Technology', status='pending',
        quantity=4, limit_price=D('100.10'), stop_price=D('97'), target_price=D('106.11'),
        entry_fee=D('0'), exit_fee=D('0'), realized_pnl=D('0'), entry_price=None, mark_price=None,
        mark_as_of=None, entry_quote_at=None, submitted_at=NOW-timedelta(seconds=60),
        expires_at=NOW+timedelta(minutes=10), evidence={})
    values.update(changes)
    return NS(**values)


def quote(price='99'):
    return NS(price=D(price), currency='USD', source='fmp', as_of=NOW, is_stale=False,
              raw_payload={'timestamp':int(NOW.timestamp())})


class CapitalRiskControlsTests(TestCase):
    def test_sparse_volume_history_is_unknown_for_existing_holdings(self):
        bars = history()
        for bar in bars[-20:-1]:
            bar.volume = None
        self.assertIsNone(compute_portfolio_market_stats(state([position()]), {'TEST':bars}).liquidity_days)

    def test_zero_volume_days_reduce_capacity(self):
        bars = history()
        normal = compute_portfolio_market_stats(state([position()]), {'TEST':bars}).liquidity_days
        for bar in bars[-20:-10]:
            bar.volume = 0
        observed = compute_portfolio_market_stats(state([position()]), {'TEST':bars}).liquidity_days
        self.assertAlmostEqual(float(observed), float(normal * 2), places=4)

    def test_return_alignment_requires_same_start_and_end_dates(self):
        bars = history(4)
        full = _returns_by_date(bars)
        missing = _returns_by_date([bars[0], bars[2], bars[3]])
        combined = _portfolio_returns({'FULL':0.5, 'MISSING':0.5}, {'FULL':full, 'MISSING':missing})
        self.assertEqual(len(combined), 1)

    def test_drawdown_crossed_by_first_fill_prevents_second_entry(self):
        r = run(cash_balance=D('9500.01'), risk_state={'day':NOW.date().isoformat(), 'baseline':'9500.01', 'blocked':False})
        first, second = order(ticker='FIRST'), order(ticker='SECOND')
        process_orders(r, [first, second], {first.instrument_id:quote(), second.instrument_id:quote()}, NOW)
        self.assertEqual(first.status, 'open')
        self.assertEqual(second.status, 'cancelled')
        self.assertEqual(r.status, 'halted')

    def test_order_decision_preserves_effective_limits(self):
        o = order()
        instrument = NS(id=o.instrument_id, ticker='TEST', name='Test', asset_class='equity', sector='Technology')
        r = run()
        decision = entry_risk(r, [], o, {o.instrument_id:instrument}, {'TEST':history()}, NOW)
        self.assertEqual(decision.get('limits'), r.policy)

    def test_proposed_risk_cash_uses_the_actual_rounded_fee(self):
        o = order()
        instrument = NS(id=o.instrument_id, ticker='TEST', name='Test', asset_class='equity', sector='Technology')
        with patch('app.services.paper_fund.risk.compute_portfolio_market_stats', wraps=compute_portfolio_market_stats) as compute:
            entry_risk(run(), [], o, {o.instrument_id:instrument}, {'TEST':history()}, NOW)
        self.assertEqual(compute.call_args.args[0].cash_balance, D('9599.39'))

    def test_partial_history_is_unknown_not_zero(self):
        stats = compute_portfolio_market_stats(state([position(), position('MISSING')]), {'TEST':history()})
        self.assertIsNone(stats.var_95_pct)
        self.assertIsNone(stats.portfolio_volatility_pct)
        self.assertIsNone(stats.liquidity_days)
        self.assertIn('MISSING', ' '.join(stats.notes))

    def test_old_and_short_history_are_rejected(self):
        for bars in (history(as_of=date(2020, 1, 1)), history(count=3), history(count=60)):
            stats = compute_portfolio_market_stats(state([position()]), {'TEST':bars})
            self.assertIsNone(stats.var_95_pct)
            self.assertIsNone(stats.portfolio_volatility_pct)

    def test_future_bars_cannot_supply_missing_history(self):
        stats = compute_portfolio_market_stats(state([position()]), {'TEST':history(253, date(2028, 1, 1))})
        self.assertIsNone(stats.var_95_pct)

    def test_adjustment_coverage_required(self):
        bars = history()
        bars[-1].adjusted_close_price = None
        self.assertIsNone(compute_portfolio_market_stats(state([position()]), {'TEST':bars}).var_95_pct)

    def test_nonfinite_adjusted_price_is_unknown(self):
        bars = history()
        bars[-1].adjusted_close_price = D('NaN')
        self.assertIsNone(compute_portfolio_market_stats(state([position()]), {'TEST':bars}).var_95_pct)

    def test_bad_raw_liquidity_price_is_unknown(self):
        bars = history()
        bars[-1].raw_payload = {'close':'not-a-price'}
        self.assertIsNone(compute_portfolio_market_stats(state([position()]), {'TEST':bars}).liquidity_days)

    def test_valid_history_produces_positive_loss_metrics(self):
        stats = compute_portfolio_market_stats(state([position()]), {'TEST':history()})
        self.assertGreater(stats.var_95_pct, 0)
        self.assertGreater(stats.expected_shortfall_95_pct, 0)

    def test_var_and_es_use_losses_not_absolute_gains(self):
        self.assertEqual(_var_pct([0.05]*60, 5), 0)
        self.assertEqual(_expected_shortfall_pct([0.05]*60, 5), 0)
        self.assertEqual(_var_pct([-0.10, -0.08, -0.06] + [0.01]*57, 5), D('6'))
        self.assertEqual(_expected_shortfall_pct([-0.10, -0.08, -0.06] + [0.01]*57, 5), D('8'))

    def test_es_tail_selection_precedes_rounding(self):
        values = [-0.0300001, -0.0200001, -0.01000051] + [0.01]*57
        self.assertAlmostEqual(float(_expected_shortfall_pct(values, 5)), 2.000023666, places=4)

    def test_withdrawal_is_not_an_investment_loss(self):
        view = build_risk_overview_from_state(state([]))
        self.assertEqual(_pre_trade_decision(view.snapshot.risk_level, [], [], view.stress_tests), 'approve')

    def test_asset_class_caps_and_policy_relaxation(self):
        limits = [NS(limit_type='max_single_equity_position_pct', threshold_value=D('5')),
                  NS(limit_type='max_etf_position_pct', threshold_value=D('25'))]
        policy = apply_account_limits(profile_policy(), limits)
        self.assertEqual(policy['max_position_pct'], 5)
        self.assertEqual(policy['max_etf_position_pct'], 10)
        limits[0].threshold_value = D('8')
        self.assertEqual(apply_account_limits(profile_policy(), limits)['max_position_pct'], 8)
        self.assertGreater(size_order(run(policy=policy), [], D('100'), 'ETF', 'etf')[0],
                           size_order(run(policy=policy), [], D('100'), 'Technology')[0])

    def test_position_count_rechecked_before_fill(self):
        r = run()
        r._external_holdings = [order(status='open', entry_price=D('100'), mark_price=D('100'), quantity=1, sector='Other') for _ in range(5)]
        o = order(quantity=1)
        process_orders(r, [o], {o.instrument_id:quote()}, NOW)
        self.assertEqual(o.status, 'cancelled')

    def test_fill_position_cap_includes_manual_shares_of_same_instrument(self):
        o = order(quantity=5)
        policy = profile_policy('high')
        policy['max_position_pct'] = 5
        r = run(policy=policy, cash_balance=D('9900'))
        r._external_holdings = [order(instrument_id=o.instrument_id, status='open', entry_price=D('100'), mark_price=D('100'), quantity=1)]
        process_orders(r, [o], {o.instrument_id:quote()}, NOW)
        self.assertEqual(o.status, 'cancelled')

    def test_daily_limit_latches_until_next_day_and_ignores_flows(self):
        r = run()
        self.assertIsNone(daily_loss_blocker(r, [], NOW))
        r.cash_balance = D('9799')
        self.assertIsNotNone(daily_loss_blocker(r, [], NOW))
        r.cash_balance = D('11000')
        r._net_flow_since_start = D('1000')
        self.assertIsNotNone(daily_loss_blocker(r, [], NOW))
        self.assertIsNone(daily_loss_blocker(r, [], NOW+timedelta(days=1)))

    def test_deposit_does_not_mask_daily_loss(self):
        r = run()
        daily_loss_blocker(r, [], NOW)
        r.cash_balance = D('10799')
        r._net_flow_since_start = D('1000')
        self.assertIsNotNone(daily_loss_blocker(r, [], NOW))

    def test_aggregate_risk_reduces_new_quantity(self):
        r = run()
        base_qty = size_order(r, [], D('100'), 'Technology')[0]
        r.policy['max_aggregate_risk_pct'] = 0.1
        self.assertLess(size_order(r, [], D('100'), 'Technology')[0], base_qty)

    def test_daily_entry_block_does_not_disable_stop_exit(self):
        r = run(cash_balance=D('9500'), risk_state={'day':NOW.date().isoformat(), 'baseline':'10000', 'blocked':True})
        o = order(status='open', quantity=5, entry_price=D('100'), mark_price=D('100'), entry_quote_at=NOW-timedelta(minutes=1))
        process_orders(r, [o], {o.instrument_id:quote('95')}, NOW)
        self.assertEqual(o.status, 'closed')
        self.assertEqual(o.exit_reason, 'stop_loss')

    def test_entry_costs_crossing_daily_limit_block_the_next_pending_fill(self):
        r = run(cash_balance=D('9800.01'), risk_state={'day':NOW.date().isoformat(), 'baseline':'10000', 'blocked':False})
        first, second = order(ticker='FIRST'), order(ticker='SECOND')
        process_orders(r, [first, second], {first.instrument_id:quote(), second.instrument_id:quote()}, NOW)
        self.assertEqual(first.status, 'open')
        self.assertEqual(second.status, 'cancelled')
        self.assertTrue(r.risk_state['blocked'])

    def test_portfolio_risk_checked_again_at_fill(self):
        o = order()
        process_orders(run(), [o], {o.instrument_id:quote()}, NOW,
                       entry_check=lambda _: {'approved':False, 'reasons':['Insufficient history']})
        self.assertEqual(o.status, 'cancelled')
        self.assertFalse(o.evidence['fill_risk']['approved'])

    def test_valid_entry_and_missing_candidate_history(self):
        o = order()
        instrument = NS(id=o.instrument_id, ticker='TEST', name='Test', asset_class='equity', sector='Technology')
        args = (run(), [], o, {o.instrument_id:instrument})
        self.assertTrue(entry_risk(*args, {'TEST':history()}, NOW)['approved'])
        self.assertFalse(entry_risk(*args, {}, NOW)['approved'])

    def test_correlated_holdings_across_sectors_block_entry(self):
        first, candidate = order(ticker='ONE', quantity=9), order(ticker='TWO', quantity=9, sector='Energy')
        instruments = {o.instrument_id:NS(id=o.instrument_id, ticker=o.ticker, name=o.ticker, asset_class='equity', sector=o.sector) for o in [first,candidate]}
        decision = entry_risk(run(), [first], candidate, instruments, {'ONE':history(), 'TWO':history()}, NOW)
        self.assertTrue(any('Correlated exposure' in reason for reason in decision['reasons']))

    def test_profile_payload_rejects_arbitrary_limits(self):
        for payload in ({'profile':'extreme','expected_profile':'medium'},
                        {'profile':'high','expected_profile':'medium','max_drawdown_pct':100}):
            with self.assertRaises(ValidationError):
                RiskProfileUpdate.model_validate(payload)
