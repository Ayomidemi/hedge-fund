# Capital and automatic execution: second audit

Reviewed October 5, 2026. Scope: the Capital ledger and reset, paper-fund
accounting and order lifecycle, radar admission, quote freshness, worker
scheduling and locking, database migrations, and the paper dashboard/queue.
This was a code and runtime review with regression testing, not a completed
market experiment or certification of investment performance.

## Findings corrected

| Priority | Finding and consequence | Correction |
| --- | --- | --- |
| High | Cash and positions were read in separate database statements while a fill could commit between them, temporarily showing invented profit or loss. | Paper and Capital overview reads now hold a shared parent-row lock while collecting balances and positions. |
| High | Reused database sessions could retain an older order, cash balance or quote after another transaction committed. | Paper reads and locked processing refresh cached ORM objects. A real database regression exercises pending → filled → closed across sessions. |
| High | Job locks used session advisory locks across commits, unsafe when a transaction pooler can move the client to a different server connection. Leftover locks can also strand replacement workers despite healthy task responses. | A dedicated transaction holds a transaction advisory lock for the job's lifetime in a separate two-integer namespace. Job-session commits cannot release it, exceptions release it automatically, and old bigint session locks cannot block it. All app workers were restarted together. |
| High | One default worker handled execution as well as slower radar, news and price jobs. Stops could wait behind unrelated work. | Execution has a separate queue and worker. Beat ticks expire to prevent a stale backlog. Startup launches both workers. |
| Medium | Order expiry used the scan timestamp even when the underlying observation was older. | Expiry is bounded by both source and scan timestamps, the order TTL, and the run end. Signals already at their expiry cannot enter the queue. |
| Medium | An older quote could be rejected for marking but still used to trigger an exit. | Regressing quotes cannot mark or exit a position and block additional risk until valid data returns. Cycle time is evaluated after acquiring its lock; an older cycle cannot rewind the heartbeat. |
| Medium | Initial sizing omitted the final cent rounding applied to a simulated stop fill. | Admission and fill checks now use the same conservative stop rounding and fees. |
| Medium | NGN trade conversion could return a USD value even when the requested portfolio currency was EUR. | Unsupported conversion fails explicitly instead of mislabeling dollars as another currency. |
| Medium | Paper orders and positions were included in quote refreshes but absent from radar's always-watched book. | Pending paper orders and open paper positions remain in radar monitoring until their lifecycle ends. |
| Low | The dashboard's extra stale-worker warning used five minutes while the backend used 90 seconds. | Both use 90 seconds. |

The locking decisions follow PostgreSQL's documented
[shared row locks and transaction advisory locks](https://www.postgresql.org/docs/current/explicit-locking.html).
PgBouncer explicitly lists session advisory locks as unsupported in
[transaction pooling](https://www.pgbouncer.org/features.html).

## Validation

- **312 backend tests passed**, including 19 PostgreSQL integration tests;
  integration tests use disposable schemas, never the configured fund database.
- Tests include overlapping fills and reads, cached sessions, a lock held across
  job commits and released after failure, recovery with a legacy session lock
  still held, source-timestamp expiry, late quotes,
  worker routing, radar lifecycle monitoring, reset owner isolation, and actual
  Alembic upgrades from the previously incomplete schema.
- Frontend lint, TypeScript checking and production build passed. The existing
  Next.js middleware-to-proxy deprecation warning remains; it does not fail the build.
- The configured database/schema health and paper-fund API returned HTTP 200.
  Both data and execution workers answered health checks and consumed their
  respective queues. After lock recovery, the actual fund heartbeat advanced
  from 12:46:47 UTC to 12:47:17 UTC on scheduled cycles, with cash unchanged.
  This verifies persisted progress rather than relying on task-success logs.
- The previously reset account's new run was running with $10,000 cash/equity,
  $0 P&L and no orders, correctly waiting for the regular US session. This audit
  did not reset or restart that run.

When deploying the job-lock change elsewhere, stop the previous workers before
starting replacements. The old and new namespaces intentionally do not contend;
mixing both worker versions would remove their mutual exclusion during rollout.

## What the test week can establish

The engine still uses a single long-only momentum rule. Its admission limits,
automatic exits and accounting are testable; a profitable trading edge has not
been established. Five positions at a 10% initial allocation cap also mean it
will normally deploy at most roughly half its starting capital, subject to
sector limits and subsequent price movement. Idle cash and no-trade days are
possible outcomes, not evidence that the engine should relax its controls.

Fills are sampled reference-price simulations. They do not model order-book
depth, partial fills, dividends, or corporate actions. Stops and the drawdown
halt are triggers, not guaranteed loss ceilings. Missing data can delay exits;
the stream's default subscription refresh is five minutes, and a newly queued
symbol may need to wait for that refresh or a valid REST quote.

At the weekly review, assess net P&L after costs, realized versus unrealized
P&L, maximum drawdown, fills and cancellations, cash utilization, signal
rejections, and quote/worker outages together. A profitable week alone does
not establish repeatability. Preserve the recorded results before changing
the strategy or starting the next comparison period.
