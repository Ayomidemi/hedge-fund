# Capital audit and $10,000 paper run

The capital dashboard, Market Radar and Opportunity Queue now share an isolated
USD paper run. A run starts with exactly $10,000 and runs for seven calendar
days. Existing portfolios, fills and cash ledgers are preserved. New default
capital portfolios also start at $10,000 unless explicit account metadata sets
a different opening balance.

## Execution flow

1. Radar records market observations. Research ideas, falling stocks and broad
   market alerts no longer become queue entries merely because they moved.
2. The paper worker screens completed radar observations for a positive,
   confirmed US equity/ETF signal, measured liquidity and a verified quote.
   Source observations must be recent; executable quotes must be at most 120
   seconds old and carry a genuine provider timestamp. Discovery timestamps
   are insufficient.
3. The engine determines whole-share size and records a limit, stop and target.
   Pending orders reserve their full cost including entry fees. Paper-run row
   locks and unique order constraints prevent concurrent duplicate spending.
4. An entry can fill only on a later observed quote within its limit after
   adverse slippage. A quote that created an order cannot also fill it. Entry
   orders expire within 30 minutes, sooner when the underlying 15-minute signal
   expires. A symbol gets at most one plan per run, including expired plans;
   this deliberately prevents repeated entries and churn during the first test.
5. Stop, profit-target, drawdown and end-of-run exits are automatic. Pausing
   cancels pending buys but leaves protective exits running. A drawdown halt
   cannot be manually resumed. End-of-run liquidation waits for valid prices
   during an open session; results remain provisional until positions close.

Celery beat schedules execution every 30 seconds on a dedicated `execution`
queue, independently of browser activity and the data worker's longer jobs.
Ticks expire after 30 seconds to avoid processing an accumulated backlog.
A stale heartbeat appears after 90 seconds. Data and capacity blockers
are visible in the UI. The stream subscription prioritizes open/pending paper
orders, and continuous streaming traffic is flushed on a bounded cadence.

## Initial experiment policy

| Control | Setting |
| --- | --- |
| Direction / market | Long only, US equities and ETFs, USD |
| Starting capital / duration | $10,000 / seven calendar days |
| Position / sector cap | 10% / 20% of equity |
| Concurrent positions and pending entries | Five total |
| Planned loss per entry | At most 0.5% of equity, including modeled costs |
| Minimum cash reserve | 20% of equity |
| Stop / profit target | 3% below / 6% above planned entry limit |
| Peak-to-trough drawdown halt | 5%; cancels entries and requests liquidation |
| Simulation costs | 10 bps adverse slippage and 5 bps fees on each side |

Limits govern admission and are rechecked before entry. Market gaps can cause
losses beyond planned risk or the drawdown threshold. This is an experimental
momentum rule, not a validated alpha model or a forecast of profit. No broker
orders are sent. Fills use sampled reference prices, without order-book depth,
partial fills, queue priority, dividends or corporate-action adjustment. Price
excursions between observations may be missed. The weekly result measures this
simulation and is not proof of achievable live returns.

US sessions follow the [NYSE published 2026–2028 calendar](https://www.nyse.com/trade/hours-calendars),
including New York daylight saving time, holidays and early closes. The calendar
fails closed outside those years and requires maintenance. The NGX discovery
calendar remains a weekday/session approximation; NGX is excluded from automatic
paper execution.

## Accounting and risk corrections

- Cash withdrawals/negative adjustments cannot overdraw funds; future cash
  entries cannot fund trading. New cash movements must use the portfolio's base
  currency. Existing foreign cash is converted for current balance displays.
- Portfolio lookups no longer commit inside risk checks and release a trade's
  lock. Risk is re-evaluated within the locked booking transaction.
- Oversells and negative-cash fills are rejected. Filled trade amounts,
  instruments, fees and dates are immutable; notes remain editable.
- Base-currency execution price and fees are stored with new trades so later
  FX changes cannot rewrite their historical cost. Same-currency legacy fills
  are backfilled. Legacy foreign fills without booked FX explicitly require
  reconciliation; current FX is not substituted for historical execution FX.
- Current valuation refuses unsupported currencies instead of treating their
  native prices as USD. Cash in streamed NAV updates follows the same conversion
  rules as the dashboard.
- Period attribution includes opening cash, reconstructs opening/closing
  inventory and uses historical marks. Missing historical prices or FX are
  reported as unavailable. Realized trade outcomes allocate entry and exit fees.
- Risk simulations retain existing holdings' market marks and expose actual
  negative/zero NAV instead of inventing a positive balance.
- Quote providers no longer substitute retrieval time for missing trade time.
  Discovery lists cannot overwrite executable quotes; ingestion rejects older
  marks and invalid prices.

The isolated paper run reconciles `equity = cash + open market value` and
`total P&L = realized P&L + unrealized P&L`, including modeled entry/exit fees.
Snapshots, orders, source evidence and completed runs remain in the database.
An archived run is readable with `GET /api/paper-fund?run_id=<uuid>`.

## Start the paper fund

Apply the database migrations with the backend environment configured:

```sh
cd backend
.venv/bin/alembic upgrade head
```

Start or restart the API and Celery worker/beat to load the new task:

```sh
./scripts/dev-backend.sh
```

The existing `HF_TIINGO_STREAM_ENABLED`/provider settings supply market prices.
A slow REST refresh alone can leave quotes outside the 120-second execution
window; the engine waits rather than fabricating freshness. Keep the API stream,
Redis, Celery worker and beat running through the run.

On Capital or Opportunity Queue, select **Start $10,000 paper fund**. Entries, share
counts and exits are then automatic. The panel shows available/reserved cash,
equity, realized/unrealized P&L, fees, maximum drawdown and actual execution
history. No one-week result exists until market observations accumulate.

## Validation

Validation on October 5, 2026: **312 backend tests passed**, including
PostgreSQL integration tests; frontend lint, TypeScript checking and production
build passed. Migration `202610050001` repairs databases where the earlier paper
migration had already been applied without `start_key`. Database health now
checks the required columns, not just connectivity or the migration version.
Regression tests reproduce that schema mismatch and verify the repair through
the API, including start retries.

The requested Capital account reset was committed after a private backup. It
clears that owner's Capital trades, positions, opportunities, paper runs and
derived history, preserves other accounts and Invest, and establishes one
$10,000 USD opening cash entry. Integration tests verify owner isolation,
transactional reset guards and backup permissions. A new paper run awaits the
**Start $10,000 paper fund** action. The owner subsequently started the new run;
the second audit verified it running at $10,000 with no orders while waiting
for the regular US session.

Unit tests cover accounting, immutable fills, precision, currency handling,
signals, quote provenance, session boundaries, reservations, costs, stop gaps,
drawdown halts, pause behavior and weekly termination. PostgreSQL tests cover
concurrent starts/cycles/withdrawals, API owner isolation, quote ordering,
historical attribution and preserved run history. All migrations were also
applied from an empty PostgreSQL database.

```sh
cd backend
.venv/bin/python -m unittest discover -s tests -v
# Use a disposable database; integration tests create/drop isolated test schemas.
HF_TEST_DATABASE_URL='postgresql+asyncpg://postgres@localhost/hedge_test' \
  .venv/bin/python -m unittest tests.integration.test_paper_fund_postgres -v
cd ../frontend
npm run lint
npx tsc --noEmit
npm run build
```

Unit fixtures and database tests validate implementation behavior, not strategy
profitability. The actual seven-day paper run is a separate experiment.

See [the second audit](capital-second-audit.md) for additional concurrency,
execution scheduling, signal expiry, and radar integration corrections.
