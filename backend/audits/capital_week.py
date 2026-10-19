"""Capture Capital performance evidence in a DB-enforced read-only transaction.

Run from backend: .venv/bin/python audits/capital_week.py --output /tmp/capital-week.json
Selects the sole Capital portfolio, or requires --portfolio-id when ambiguous.
Does not call account services, refresh providers, run execution, or change mode.
The local output contains financial records; do not commit it to the repository.
"""
import argparse
import asyncio
import json
from pathlib import Path
import sys
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from app.db.session import engine

QUERIES = {
    'runs': '''SELECT id, status, starting_cash, cash_balance, net_contributions_at_start,
        started_at, ends_at, last_cycle_at, completed_at, high_water_equity,
        max_drawdown_pct, policy, risk_state, blockers FROM paper_fund_runs
        WHERE portfolio_id=:pid ORDER BY started_at''',
    'limits': '''SELECT limit_type, threshold_value, is_active FROM risk_limits WHERE portfolio_id=:pid''',
    'instruments': '''SELECT ticker, name, asset_class, sector, industry, exchange, currency
        FROM instruments WHERE id IN (SELECT instrument_id FROM trades WHERE portfolio_id=:pid)''',
    'cash': '''SELECT entry_date, amount, currency, entry_type, source_reference, created_at
        FROM cash_ledger_entries WHERE portfolio_id=:pid ORDER BY entry_date, created_at''',
    'trades': '''SELECT t.id, i.ticker, t.trade_date, t.side, t.status, t.quantity,
        t.executed_price, t.executed_price_base, t.fees, t.fees_base, t.broker_reference,
        t.idempotency_key FROM trades t JOIN instruments i ON i.id=t.instrument_id
        WHERE t.portfolio_id=:pid ORDER BY t.trade_date, t.created_at''',
    'positions': '''SELECT i.ticker, i.asset_class, i.sector, p.quantity, p.average_cost,
        p.market_value, p.unrealized_pnl, p.updated_at, q.price quote_price, q.as_of quote_as_of,
        q.source quote_source, q.is_stale quote_stale FROM positions p
        JOIN instruments i ON i.id=p.instrument_id LEFT JOIN instrument_quotes q ON q.instrument_id=i.id
        WHERE p.portfolio_id=:pid AND p.quantity>0''',
    'orders': '''SELECT o.id, o.run_id, o.ticker, o.status, o.quantity, o.limit_price,
        o.entry_price, o.exit_price, o.stop_price, o.target_price, o.entry_fee, o.exit_fee,
        o.realized_pnl, o.mark_price, o.mark_as_of, o.submitted_at, o.opened_at, o.closed_at,
        o.expires_at, o.entry_quote_at, o.exit_quote_at, o.exit_reason, o.evidence
        FROM paper_orders o JOIN paper_fund_runs r ON r.id=o.run_id
        WHERE r.portfolio_id=:pid ORDER BY o.submitted_at''',
    'snapshots': '''SELECT s.run_id, s.recorded_at, s.equity, s.cash_balance,
        s.realized_pnl, s.unrealized_pnl, s.drawdown_pct FROM paper_equity_snapshots s
        JOIN paper_fund_runs r ON r.id=s.run_id WHERE r.portfolio_id=:pid
        AND s.recorded_at >= now()-interval '15 days' ORDER BY s.recorded_at''',
    'radar_runs': '''SELECT id, started_at, finished_at, status, jurisdictions_scanned,
        working_set_count, catalog_count, flagged_count, vendor_calls FROM radar_runs
        WHERE started_at>=now()-interval '7 days' ORDER BY started_at''',
    'priority_observations': '''SELECT s.run_id, s.ticker, s.jurisdiction, s.currency,
        s.asset_class, s.price, s.change_pct, s.volume_ratio, s.volume, s.avg_volume,
        s.radar_priority, s.as_of, s.source_as_of, s.carried_forward, s.stale_reason,
        s.evidence->>'avg_dollar_volume' avg_dollar_volume,
        s.evidence->>'move_scope' move_scope,
        s.evidence->>'price_return_zscore' price_return_zscore,
        s.evidence->>'volume_zscore' volume_zscore,
        s.evidence->>'sector_relative_return_pct' sector_relative_return_pct
        FROM radar_snapshots s JOIN radar_runs r ON r.id=s.run_id
        WHERE r.started_at>=now()-interval '7 days' AND r.status='completed'
        AND s.radar_priority IN ('P0','P1') ORDER BY s.as_of''',
    'history_preparation': '''SELECT status, last_bar_date, count(*) names, min(last_attempt_at) oldest_attempt,
        max(last_attempt_at) latest_attempt FROM radar_history_preparation GROUP BY status,last_bar_date''',
    'benchmark_bars': '''SELECT i.ticker, b.bar_date, b.source, b.close_price, b.adjusted_close_price
        FROM market_price_bars b JOIN instruments i ON i.id=b.instrument_id
        WHERE i.ticker IN ('SPY','QQQ') AND b.bar_date>=current_date-15 ORDER BY i.ticker,b.bar_date,b.source''',
    'log_counts': '''SELECT event, level, count(*) occurrences, min(created_at) first_at,
        max(created_at) last_at FROM system_log_entries WHERE owner_user_id=
        (SELECT owner_user_id FROM portfolios WHERE id=:pid)
        AND created_at>=now()-interval '7 days' GROUP BY event,level ORDER BY occurrences DESC''',
}

async def capture(portfolio_id, output):
    try:
        async with engine.connect() as connection:
            async with connection.begin():
                await connection.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                await connection.execute(text("SET LOCAL statement_timeout = '30s'"))
                accounts = (await connection.execute(text('''SELECT id, name, base_currency, initial_capital,
                    trading_mode, risk_profile FROM portfolios'''))).mappings().all()
                selected = [a for a in accounts if portfolio_id is None or str(a['id']) == portfolio_id]
                if len(selected) != 1:
                    raise ValueError('Specify --portfolio-id identifying exactly one Capital portfolio.')
                account = dict(selected[0])
                result = {'as_of': await connection.scalar(text('SELECT now()')), 'account': account}
                for name, sql in QUERIES.items():
                    rows = (await connection.execute(text(sql), {'pid': account['id']})).mappings().all()
                    result[name] = [dict(row) for row in rows]
                    print(f'{name}: {len(rows)} records', flush=True)
        # Restrict file permissions because this includes the user's financial history.
        import os
        fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(result, handle, default=str, indent=2)
        print(f'Read-only evidence saved: {output}')
    finally:
        await engine.dispose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--portfolio-id', type=lambda value: str(UUID(value)))
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        asyncio.run(capture(args.portfolio_id, args.output))
    except Exception as exc:
        # DB connection exceptions may embed credentials: never print their text.
        print(f'Audit capture failed: {type(exc).__name__}', file=sys.stderr)
        raise SystemExit(1)
