"""Offline diagnostics from capital_week.py evidence; no provider or DB access."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.paper_fund.calendar import session_bounds, market_blocker
from app.services.market_radar.execution import execution_rejection


def dt(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def market_seconds(start, end):
    if end <= start:
        return 0.0
    day = start.astimezone(timezone.utc).replace(hour=16, minute=0, second=0, microsecond=0)
    total = 0.0
    while day.date() <= end.astimezone(timezone.utc).date():
        bounds = session_bounds(day)
        if bounds:
            left, right = max(start, bounds[0]), min(end, bounds[1])
            total += max(0.0, (right-left).total_seconds())
        day += timedelta(days=1)
    return total


def exposure(trades, start, end):
    """Time-weighted entry cost of held shares, not a mark-to-market return.

    Includes holdings established before the window. Concurrent holdings add;
    sales release average acquisition cost, not their sale proceeds.
    """
    quantities, costs = defaultdict(lambda: D(0)), defaultdict(lambda: D(0))
    weighted = D(0)
    prior = start
    maximum = D(0)
    max_names = 0
    for trade in sorted(trades, key=lambda row: dt(row['trade_date'])):
        if trade['status'] != 'filled':
            continue
        at = dt(trade['trade_date'])
        if at > end:
            break
        if at >= start:
            maximum = max(maximum, sum(costs.values(), D(0)))
            max_names = max(max_names, sum(q > 0 for q in quantities.values()))
            weighted += sum(costs.values(), D(0))*D(str(market_seconds(prior, at)))
            prior = at
        ticker, quantity = trade['ticker'], D(trade['quantity'])
        price = D(trade['executed_price_base'] or trade['executed_price'])
        if trade['side'].lower() == 'buy':
            quantities[ticker] += quantity
            costs[ticker] += quantity*price
        else:
            if quantities[ticker] < quantity:
                raise ValueError('Trade history cannot reconcile the sell quantity.')
            costs[ticker] -= costs[ticker]/quantities[ticker]*quantity
            quantities[ticker] -= quantity
        if at >= start:
            maximum = max(maximum, sum(costs.values(), D(0)))
            max_names = max(max_names, sum(q > 0 for q in quantities.values()))
    weighted += sum(costs.values(), D(0))*D(str(market_seconds(prior, end)))
    maximum = max(maximum, sum(costs.values(), D(0)))
    max_names = max(max_names, sum(q > 0 for q in quantities.values()))
    seconds = market_seconds(start, end)
    return {'market_hours': seconds/3600,
            'average_entry_cost_held': weighted/D(str(seconds)) if seconds else None,
            'maximum_entry_cost_after_trade': maximum, 'max_names_after_trade': max_names}


def signal_screen(data):
    """Stored signal screen only. Synthetic matching quotes isolate signal gates.

    Passing is NOT execution approval: historical executable quotes, account
    capacity, confirmation at fill and risk checks are unavailable here.
    """
    runs = {r['id']: r for r in data['radar_runs']}
    counts, tickers, by_day = Counter(), defaultdict(set), defaultdict(Counter)
    passed_by_day = defaultdict(Counter)
    passed_after_close = Counter()
    orders = data['orders']
    fund_runs = {r['id']: r for r in data['runs']}
    for row in data['priority_observations']:
        run = runs[row['run_id']]
        at = dt(run['finished_at'] or run['started_at'])
        if market_blocker(at):
            continue
        evidence = {key: row[key] for key in ('avg_dollar_volume', 'move_scope',
                    'price_return_zscore', 'volume_zscore', 'sector_relative_return_pct')}
        snapshot = NS(**{**row, 'as_of': dt(row['as_of']),
                        'source_as_of': dt(row['source_as_of']) if row['source_as_of'] else None,
                        'evidence': evidence})
        # Local synthetic input; no quote is persisted or sent to execution.
        quote = NS(price=row['price'], currency=row['currency'], is_stale=False, source='fmp',
                   as_of=at, raw_payload={'timestamp': at.timestamp()},
                   previous_close=None, change_pct=row['change_pct'])
        reason = execution_rejection(snapshot, quote, at) or 'Passed stored signal gates; execution unverified'
        counts[reason] += 1
        tickers[reason].add(row['ticker'])
        by_day[at.date().isoformat()][reason] += 1
        if reason == 'Passed stored signal gates; execution unverified':
            passed_by_day[at.date().isoformat()][row['ticker']] += 1
            if any(o['ticker'] == row['ticker'] and o['closed_at'] and dt(o['closed_at']) < at
                   and dt(fund_runs[o['run_id']]['started_at']) <= at < dt(fund_runs[o['run_id']]['ends_at'])
                   for o in orders):
                passed_after_close[row['ticker']] += 1
    return {'observations': dict(counts), 'unique_symbols_by_first_gate': {k: len(v) for k,v in tickers.items()},
            'passed_symbols': sorted(tickers['Passed stored signal gates; execution unverified']),
            'by_day': dict(by_day), 'passed_symbols_by_day': dict(passed_by_day),
            'passed_observations_after_same_run_close': dict(passed_after_close)}


def summarize(data):
    now = dt(data['as_of'])
    closed = [o for o in data['orders'] if o['status'] == 'closed']
    wins = [D(o['realized_pnl']) for o in closed if D(o['realized_pnl']) > 0]
    losses = [D(o['realized_pnl']) for o in closed if D(o['realized_pnl']) < 0]
    cash = sum((D(e['amount']) for e in data['cash']), D(0))
    contributions = sum((D(e['amount']) for e in data['cash'] if e['entry_type'] not in {'trade_buy','trade_sell'}), D(0))
    equity = cash + sum((D(p['market_value']) for p in data['positions']), D(0))
    snapshots = data['snapshots']
    gaps = []
    for a,b in zip(snapshots,snapshots[1:]):
        left,right=dt(a['recorded_at']),dt(b['recorded_at'])
        if (right-left).total_seconds()>900 and market_seconds(left,right)>0:
            gaps.append({'from':left,'to':right,'market_hours_between_snapshots':market_seconds(left,right)/3600})
    by_run=[]
    for run in data['runs']:
        orders=[o for o in data['orders'] if o['run_id']==run['id']]
        by_run.append({'started_at':run['started_at'], 'status':run['status'],
                       'closed_pnl':sum((D(o['realized_pnl']) for o in orders if o['status']=='closed'),D(0)),
                       'orders':dict(Counter(o['status'] for o in orders)),
                       'deployment':exposure(data['trades'],dt(run['started_at']),dt(run['completed_at']) if run['completed_at'] else now)})
    return {'as_of':now,'cash':cash,'equity':equity,'contributions':contributions,'total_pnl':equity-contributions,
            'closed_pnl':sum(wins)+sum(losses),'unrealized_net_entry_fees':equity-contributions-sum(wins)-sum(losses),
            'closed_trades':len(closed),'wins':len(wins),'losses':len(losses),'winning_pnl':sum(wins),
            'losing_pnl':sum(losses),'profit_factor':sum(wins)/-sum(losses) if losses else None,
            'fees':sum((D(t['fees_base'] or t['fees']) for t in data['trades'] if t['status']=='filled'),D(0)),
            'last_seven_days_deployment':exposure(data['trades'],now-timedelta(days=7),now),
            'runs':by_run,'snapshot_gaps_over_15_minutes':gaps,'signal_screen':signal_screen(data)}

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence')
    args=parser.parse_args()
    print(json.dumps(summarize(json.loads(Path(args.evidence).read_text())),default=str,indent=2))
