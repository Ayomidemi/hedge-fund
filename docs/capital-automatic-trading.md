# Automatic trading in Capital

Capital has one cash ledger, one position book, and one trade journal. The
Manual / Automatic toggle changes how trades are initiated, not which account
they use. The current execution adapter simulates trades; it sends no live
broker orders.

- **Automatic:** the engine consumes eligible radar signals, reserves existing
  Capital cash, sizes limit orders, and manages their exits. Each fill books a
  normal Capital trade and cash movement in the same locked transaction.
- **Manual:** pending automatic buys are cancelled and all automatic buys and
  sells stop, including stop-loss, target and timed exits. Existing holdings
  remain in Capital. Price updates and performance monitoring continue.
- Switching back resumes the same review period when possible. Starting a new
  seven-day review uses current equity and cash; it never deposits another
  $10,000 or deletes previous history. A latched risk halt cannot be cleared by
  switching modes. An expired period completes its scheduled liquidation when
  automation is enabled, then returns to Manual.

Manual trade entry requires Manual mode. Manually trading an instrument
releases that instrument's existing automatic plan; any remaining shares stay
in the normal position book under manual management. This prevents an older
automatic sell quantity from overselling a position after a partial manual sale.

The account's holdings count toward position and sector capacity. Automation
uses the stricter common position, sector and cash limits from Capital and its
execution policy. Withdrawals cannot spend cash reserved for pending orders.
Deposits and withdrawals are excluded from profit and loss and from changes in
the review period's drawdown baseline.

The dashboard, queue, and normal Capital endpoints read the same ledger.
Performance metrics represent the account; the equity chart records observations
during the current review period. Execution-plan rows are order-management
records, not a second source of cash or inventory.

## Upgrade and run

Apply `.venv/bin/alembic upgrade head` from the backend directory.
Migration `202610050002` adds the persisted trading mode and execution/account
link without adding cash. Existing active runs can be attached through
`start_run`; historical fills are booked once using order/side idempotency keys.
An unlinked legacy run cannot execute until attached. If the existing account
cannot fund its legacy fills, attachment rolls back instead of creating cash.

Start `./scripts/dev-backend.sh` to run the API, data worker, dedicated execution
worker and scheduler. Capital's toggle controls the account from the dashboard,
radar or Opportunity Queue. Backend API: `POST /api/operating-core/trading-mode`
with `{"mode":"manual"}` or `{"mode":"automatic"}`.

Validation: 322 backend tests passed, including shared-ledger fills, mode changes,
cash reservations, tighter Capital risk limits, legacy migration, partial manual
sales, owner isolation and real PostgreSQL migrations/concurrency. Frontend lint,
TypeScript checking and production build also passed.

The strategy remains an unvalidated long-only momentum rule. Simulated fills,
fees and slippage do not establish achievable live returns; stale data can delay
execution and gaps can exceed planned stop losses.
