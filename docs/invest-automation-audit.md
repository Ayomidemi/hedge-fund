# Invest automatic trading readiness audit

7 October 2026. Scope: audit and implementation design for **a separate Invest paper account**, as requested. This audit does not enable automation, reset balances, transfer Capital money, or alter existing orders. Production code changes already present from the Capital audit were preserved.

## Decision

Invest can support automatic paper trading, but adding a toggle to the current instant-fill broker would produce unreliable execution and accounting. Reuse the market-data, signal-validation, sizing and order-transition logic from Capital, with an Invest-specific account/ledger adapter. Keep separate account locks, budgets, orders, positions, performance and permissions. Do not call Capital's account-bound engine or `/paper-fund` endpoints on behalf of Invest users.

The read-only account check found an active USD PAPER account with **$90,542.24 cash, three open positions and five filled orders**. Its configured starting cash is $100,000; this is not Capital's $10,000 account. The automatic allocation remains an explicit setup decision. Existing cash and holdings should be preserved, with automation disabled by default until the account is configured.

## Findings, ordered by importance

### 1. Critical: account locks can preserve an obsolete cash balance

`lock_retail_account` in `backend/app/db/locks.py` and `PaperBrokerProvider._load_account(for_update=True)` take row locks without refreshing objects already loaded in the SQLAlchemy session. Unlike the Capital lock, neither uses `populate_existing=True`.

**Reproduced in an isolated PostgreSQL schema:** two sessions read $100. The first locks and commits a reduction to $40. The second obtains the account lock, but its ORM account still reports $100, while a scalar database read reports $40. The broker helper separately reproduced $40 in memory versus $20 committed. Manual orders plus an automatic worker would make this race more likely. Cash updates based on the stale object can lose another transaction's debit.

**Required:** refresh state on acquiring every account write lock; re-evaluate cash, reservations and position quantities under that lock. Add concurrent manual/automatic buy, sell, deposit and reset integration tests, checking both cash and transaction reconciliation.

### 2. High: executable limit orders do not exist on the Invest path

`InvestOrderCreate` has no `limit_price`; an incoming `limit_price` is silently discarded by schema validation. `accounts.submit_order` does not forward one. Although the database and broker protocol have a limit-price field, `PaperBrokerProvider.submit_order` always creates a `market` order already marked `FILLED` at the current mark. There is no waiting-for-limit-price transition, expiry or later-observation requirement.

The deployed policy currently allows only market orders. Merely adding `limit` to its configuration would not implement limit execution. The `instant_fills` configuration is parsed but not used to implement an alternative lifecycle.

**Required:** validate and persist order type, price, time-in-force and expiry; implement submitted/pending/filled/cancelled/expired/rejected transitions; separate order acceptance from fills. Preserve existing client compatibility explicitly, rather than silently reinterpreting a limit request.

### 3. High: current risk checks permit unsuitable unattended fills

`services/invest/risk.py` makes closed-market trading a warning, not a blocker. A probe of a $9,000 buy against $10,000 cash, during a closed session, produced zero blockers. Concentration is also advisory. There are no equivalent automatic sector, portfolio exposure, cash reserve, per-trade loss or drawdown gates here.

`get_cached_quote_price` checks only the stored `is_stale` flag, not current age. The probe accepted a three-day-old timestamp with the flag cleared. Its fetch fallback also returns a price without an execution-age gate, and can select the first returned symbol if the requested symbol is absent. This helper is a valuation/cache helper, not a sufficient execution gate.

**Required:** account-active and PAPER-provider checks; exact-symbol/currency verification; market-calendar and provider-time validation; hard risk limits before both reservation and fill. Reuse the validated Tiingo-reference handling and disclose simulated pricing. Keep closed, stale, missing and future-dated data fail-closed.

### 4. High: pending orders cannot reserve cash or stock

`PaperBrokerProvider._balances` always returns buying power equal to cash and pending cash equal to zero. That matches today's instant-fill implementation, but cannot safely support unfilled automatic orders. Cash top-ups/resets and manual orders do not coordinate with an automation reservation book. Pending Invest orders are also absent from the live-price universe; only Invest positions/watchlists and Capital's `PaperOrder` rows are included.

**Required:** reserve worst-case buy notional plus modeled fees when accepting an order; reserve sell quantity where necessary; release exactly once on fill/cancel/expiry. Manual trades and cash actions must use the same spendable balances. Add pending Invest orders to prioritized stream subscriptions and execution quote refreshes. Block or atomically stop/reconcile automation before a reset.

### 5. High: displayed return is not complete trading performance

`accounts.get_home` sets `total_return` to the sum of **unrealized** P/L on current holdings. It excludes realized results. `_apply_sell` updates realized P/L on the position, then deletes that position when fully closed. Transactions retain cash movements, but there is no immutable per-fill realized-performance record being used by the displayed total.

After an automated strategy closes all positions, the existing display can show zero return despite realized gains or losses. Instant fills also omit the Capital simulator's fees/slippage, making performance comparisons inconsistent.

**Required:** durable fill/cost-basis accounting, fees, realized and unrealized P/L, net contributions, account snapshots and flow-adjusted weekly performance. Closed trades must survive position deletion. Deposit and reset events must not look like investment returns. Reconcile cash to transactions and account equity to cash plus marked positions.

### 6. Required capability: account-specific control and strategy state

`RetailAccount` has no trading mode, automation allocation or strategy version. There is no Invest scheduler, managed-position exit plan, heartbeat, daily loss state, weekly evaluation state or automatic/manual order origin. Current Capital execution is explicitly bound to its `Portfolio` and ledger. Existing Invest owner filtering and order idempotency indexes are useful foundations, but do not supply this missing lifecycle.

**Required:** separate Invest run/strategy state, persisted mode, allocation and hard risk policy; idempotent signal/order intents; restart recovery; account-scoped leases/locks; a visible heartbeat and execution blockers. Do not expose Capital permissions or internal account data through Invest routes.

### 7. Product scope: bonds need a different automatic strategy

Invest supports bills, bonds, cash-equivalents and foreign-currency products. Current fixed-income paper fills can use dirty-price/model marks. The inspected worker schedule has no automatic coupon, maturity redemption or reinvestment lifecycle. A US-equity momentum engine cannot be applied unchanged to these instruments.

**Recommended first release:** USD listed equities/ETFs with verified data and the existing bounded paper-execution policy. Keep current manual holdings and fixed-income positions in total account exposure calculations. Separately design an income strategy with maturity ladders, coupon/redemption cashflows, dirty/clean price handling, quote-quality eligibility, minimum denominations, settlement and FX controls. Model-derived fixed-income returns must be labeled as such.

## Proposed implementation

| Layer | Concrete change |
| --- | --- |
| Shared execution core | Extract pure sizing, fee/slippage, freshness, calendar, limit-fill and exit transitions from the Capital service. Keep ledger mutations behind account adapters. Capital's existing tests must continue passing. |
| Invest state | Add persisted mode/allocation/policy version, run records, equity snapshots and trade plans linked to canonical `RetailOrder` entries/exits. Keep actual cash/positions/transactions in existing Invest tables. Avoid another shadow balance. |
| Order service | Add validated limits, expiry, fees, price provenance, automatic/manual origin, plan links and account-scoped unique intent keys. A fill, its cash movement, position change and reservation release commit together. |
| Account consistency | Repair both lock-refresh paths; reserve buying power and sell quantities; coordinate manual orders, automatic orders, cash movements, cancellations and resets. |
| Worker | Add an Invest execution task on the execution queue, with a distinct job lock and per-account idempotency. Scan only enabled, active PAPER accounts. Share quote fetching across accounts and obtain network data before account locks. Exceptions in one account must not stop the others. |
| API/security | Add owner-scoped `/invest/automation` status and mode/configuration endpoints guarded by `require_invest_user`. Validate provider, account status, budget and policy server-side. |
| UI | One Manual/Automatic toggle backed by server state; show allocated budget, cash, reserved cash, available buying power, pending orders, managed positions, realized/unrealized P/L and last worker check. Existing manual holdings remain visible. Clearly identify automatic orders and why an enabled account is waiting. |

Manual mode should cancel unfilled automatic entries and stop automatic buys/sells without selling or deleting positions just because the toggle changed. An already committed fill remains a fill. Persist the transition under the account lock. The UI must make the pause's effect on planned exits explicit. A manual sale must resize or release the corresponding automatic plan so it cannot later oversell the same shares.

The worker must size against both the configured automation allocation and the whole account's cash/exposure limits. Separate Invest cash does not mean existing manual holdings can be ignored. An automatic position should never spend Capital funds or create a deposit in either account.

## Delivery sequence and acceptance criteria

1. **Fix financial invariants first:** fresh locked state, exact-once cash/fill accounting, complete realized P/L, hard execution gates. Reproduce and close the six readiness probes below.
2. **Implement the Invest order lifecycle:** limits, reservations, expiry, later-observation fills and managed exits. Test each transition independently of a running worker.
3. **Add shared-core adapter and worker:** simulate duplicate delivery, worker crashes/restarts, overlapping cycles and provider failures. Verify Capital and Invest cannot touch each other's books, even for the same user.
4. **Expose control and reporting:** server-persisted toggle and explicit budget, common balances across Home/Portfolio/Cash/Orders, clear blocked/stale states, weekly realized/unrealized results.
5. **Run a bounded paper evaluation:** preserve the current Invest account, record starting equity/net flows and an explicit allocation, observe actual scheduled entries and exits, and reconcile the report to the ledger. Do not declare readiness solely from an instant-fill unit test.

Must-pass scenarios include simultaneous manual and automatic orders, competing accounts on the same symbol, duplicate signals and retries, fill-versus-cancel, manual partial sells, cash resets with pending entries, mode changes during a cycle, stale/future/wrong-symbol quotes, market holidays, insufficient fees/reserves, unavailable FX, gaps through stops, closed-position realized P/L and deposits during a weekly evaluation.

## Evidence and validation

- Read-only inspection of the existing Invest account/policies; no runtime configuration or financial records changed.
- Existing Invest unit suite: **61 tests passed**. These do not establish automatic-trading readiness.
- `backend/audits/invest_automation.py`: **six readiness gaps reproduced**. Four API/risk/cache/balance probes use local objects and mocks; two lock probes use real PostgreSQL sessions in a disposable schema. All six reported `gap_present: true`; these are findings, not six passing safety tests.
- The lock probe creates and drops its own schema and rejects non-local or non-`*_test` database URLs. Run from `backend` with `HF_TEST_DATABASE_URL` explicitly pointing to the disposable test database.
- A separate import-order issue surfaced when importing the broker directly: brokerage and Invest package initializers eagerly import each other. The probe uses the application's working import order. Remove that coupling while extracting a reusable core so a new standalone worker can import its services reliably.

No automatic Invest trading has been enabled by this audit. The next implementation starts with the confirmed cash-lock defect, not the UI toggle.
