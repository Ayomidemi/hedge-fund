"""Deterministic Capital risk audit; no database, network, or account writes.

Run from backend: .venv/bin/python audits/capital_risk.py
These probes report whether previously identified gaps remain. Regression
assertions live in tests/unit/test_capital_risk_controls.py.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.paper_fund.engine import POLICY, process_orders, size_order
from app.services.paper_fund.capital import capital_policy
from app.services.risk.risk_centre import (
    PortfolioRiskState, RiskPosition, build_risk_overview_from_state,
    compute_portfolio_market_stats, _pre_trade_decision, _var_pct,
)

NOW = datetime(2026, 10, 7, 15, tzinfo=timezone.utc)


def report(name, gap, **evidence):
    print(json.dumps(dict(probe=name, gap_present=gap, **evidence), default=str))


def position(ticker):
    return RiskPosition(uuid4(), ticker, ticker, 'equity', ticker, D('5'),
                        D('100'), D('500'), D('0'))


def state(positions):
    invested = sum((p.market_value for p in positions), D('0'))
    return PortfolioRiskState(uuid4(), 'Audit', NOW, NOW.date(), D('10000'),
                              D('10000') - invested, invested, positions)


def bars(year=2026):
    return [NS(bar_date=date(year, 6, 1) + timedelta(days=i),
               adjusted_close_price=D('100'), close_price=D('100'), volume=100000)
            for i in range(128) if (date(year, 6, 1) + timedelta(days=i)).weekday() < 5]


async def main():
    partial = compute_portfolio_market_stats(state([position('KNOWN'), position('MISSING')]),
                                             {'KNOWN': bars()})
    report('missing_holding_history_treated_as_zero_return', partial.var_95_pct == 0,
           var_pct=partial.var_95_pct, volatility_pct=partial.portfolio_volatility_pct,
           liquidity_days=partial.liquidity_days, notes=partial.notes)
    stale = compute_portfolio_market_stats(state([position('KNOWN')]), {'KNOWN': bars(2020)})
    report('old_history_accepted_without_freshness_warning', stale.var_95_pct is not None and not stale.notes,
           last_bar=str(bars(2020)[-1].bar_date), as_of=str(NOW.date()), notes=stale.notes)
    short = compute_portfolio_market_stats(state([position('KNOWN')]), {'KNOWN': bars()[:3]})
    report('volatility_published_from_two_returns', short.portfolio_volatility_pct is not None,
           returns=2, volatility_pct=short.portfolio_volatility_pct)
    all_gains = _var_pct([0.05] * 60, percentile=5)
    report('gain_only_var_exceeds_absolute_loss_limit', abs(all_gains) > 4,
           reported_var_pct=all_gains, limit_pct=4)
    session = NS(scalar=AsyncMock(return_value='medium'), scalars=AsyncMock(return_value=[
        NS(limit_type='max_single_equity_position_pct', threshold_value=D('5')),
        NS(limit_type='max_etf_position_pct', threshold_value=D('25'))]))
    effective = await capital_policy(session, uuid4(), POLICY)
    report('equity_and_etf_caps_collapsed', effective.get('max_etf_position_pct', effective['max_position_pct']) == 5,
           stock_cap=effective['max_position_pct'], etf_cap=effective.get('max_etf_position_pct'))
    session.scalars.return_value = [NS(limit_type='max_single_equity_position_pct', threshold_value=D('8'))]
    revised = await capital_policy(session, uuid4(), effective)
    report('policy_can_tighten_but_cannot_relax', revised['max_position_pct'] != 8,
           requested_equity_cap=8, resulting_cap=revised['max_position_pct'])
    cash_only = build_risk_overview_from_state(state([]))
    decision = _pre_trade_decision(cash_only.snapshot.risk_level, [], [], cash_only.stress_tests)
    report('withdrawal_stress_forces_review_for_cash_only_fund', decision == 'reduce_or_review',
           decision=decision, stress=[s.scenario_name for s in cash_only.stress_tests if s.severity == 'reduce'])
    run = NS(policy=effective, cash_balance=D('10000'), starting_cash=D('10000'))
    quantity, limit, stop, target = size_order(run, [], D('10'), 'Technology')
    report('effective_sizing_example', False, quantity=quantity, entry_limit=limit,
           stop=stop, target=target, gross_notional=quantity * limit)
    # A pending order can predate five manual holdings. Fill must recheck count.
    run.status = 'running'
    run.ends_at = NOW + timedelta(days=1)
    run.high_water_equity = D('10500')
    run.max_drawdown_pct = D('0')
    run.halt_reason = None
    run._external_holdings = [NS(status='open', mark_price=D('100'), entry_price=D('100'),
        limit_price=D('100'), quantity=1, entry_fee=D('0'), sector='Other') for _ in range(5)]
    order = NS(status='pending', instrument_id=uuid4(), ticker='TEST', sector='Technology',
        quantity=1, limit_price=D('100.10'), stop_price=D('97'), target_price=D('106.11'),
        submitted_at=NOW-timedelta(seconds=60), expires_at=NOW+timedelta(minutes=10),
        entry_fee=D('0'), exit_fee=D('0'), realized_pnl=D('0'), mark_price=None)
    quote = NS(price=D('99'), currency='USD', source='fmp', as_of=NOW,
               is_stale=False, raw_payload={'timestamp':int(NOW.timestamp())})
    process_orders(run, [order], {order.instrument_id:quote}, NOW)
    report('position_count_not_rechecked_at_fill', order.status == 'open',
           existing_positions=5, limit=effective['max_positions'], order_after_cycle=order.status)


if __name__ == '__main__':
    asyncio.run(main())
