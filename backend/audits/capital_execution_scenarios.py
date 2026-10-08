"""Deterministic model experiments, separate from the running execution policy.

Run from backend: .venv/bin/python audits/capital_execution_scenarios.py
Synthetic observations test loss sensitivity, not strategy profitability.
"""
from decimal import Decimal as D, ROUND_FLOOR
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.paper_fund.engine import size_order
from app.services.risk.policy import profile_policy


def atr_stop_pct(completed_bars, entry_price, multiplier=D('2')):
    """Use only the supplied pre-entry bars, never the subsequent replay path."""
    if len(completed_bars) < 15:
        raise ValueError('ATR needs at least 15 completed bars.')
    ranges = [max(high-low, abs(high-previous[2]), abs(low-previous[2]))
              for previous, (high, low, close) in zip(completed_bars[-15:], completed_bars[-14:])]
    return sum(ranges) / len(ranges) * multiplier / entry_price * 100


def replay_exit(quantity, entry, stop, observations, *, fee_bps=D('5'), slippage_bps=D('10')):
    """Reference stop trigger with bid-side partial fills and remaining inventory.

    Each observation supplies (reference, bid, available shares, fresh). Capacity
    is explicit synthetic data. Unlike the live simulator this exercise models
    partial exits; it does not claim the provider supplies executable depth.
    """
    remaining, proceeds, triggered = quantity, D('0'), False
    for reference, bid, capacity, fresh in observations:
        if not fresh:
            continue
        triggered = triggered or reference <= stop
        if not triggered or remaining == 0:
            continue
        fill_quantity = min(remaining, capacity)
        price = (bid * (1 - slippage_bps / 10000)).quantize(D('.01'), rounding=ROUND_FLOOR)
        proceeds += fill_quantity * price * (1 - fee_bps / 10000)
        remaining -= fill_quantity
    cost = quantity * entry * (1 + fee_bps / 10000)
    return {'remaining_shares':remaining, 'net_cash_pnl_if_flat':str((proceeds-cost).quantize(D('.01'))) if not remaining else None}


def main():
    policy = profile_policy()
    policy['max_position_pct'] = 5
    run = NS(policy=policy, cash_balance=D('10000'), starting_cash=D('10000'))
    fixed = size_order(run, [], D('10'), 'Technology')
    # High-volatility pre-entry history; subsequent gap data is not used to size.
    before_entry = [(D('10.4'), D('9.6'), D('10'))] * 15
    alternative = {**policy, 'stop_loss_pct':float(atr_stop_pct(before_entry, D('10')))}
    atr = size_order(NS(policy=alternative, cash_balance=D('10000'), starting_cash=D('10000')), [], D('10'), 'Technology')
    assert atr[0] < fixed[0], 'A wider ATR stop must reduce share count at fixed risk budget.'
    qty, entry, stop, _ = fixed
    normal = replay_exit(qty, entry, stop, [(stop, stop-D('.01'), qty, True)])
    gap = replay_exit(qty, entry, stop, [(D('8'), D('7.98'), qty, True)])
    partial = replay_exit(qty, entry, stop, [(stop, stop-D('.04'), 10, True)])
    delayed = replay_exit(qty, entry, stop, [(stop, stop-D('.01'), qty, False), (D('8'), D('7.98'), qty, True)])
    assert D(gap['net_cash_pnl_if_flat']) < D(normal['net_cash_pnl_if_flat'])
    assert partial['remaining_shares'] == qty-10
    assert partial['net_cash_pnl_if_flat'] is None
    assert delayed == gap
    print(json.dumps({'synthetic_only':True, 'live_stop_policy_changed':False,
        'fixed_stop_shares':fixed[0], 'atr_stop_pct':alternative['stop_loss_pct'], 'atr_shares':atr[0],
        'normal_stop':normal, 'gap_stop':gap, 'partial_exit':partial, 'stale_then_gap':delayed}, indent=2))


if __name__ == '__main__':
    main()
