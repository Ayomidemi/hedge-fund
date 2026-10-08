# Performance and execution audit — 6 October 2026

## Measured read performance

Direct service calls against the configured database for the same existing account, with a SQL hook rejecting writes and each session rolled back. These are single samples, not browser navigation benchmarks or production percentiles. Database latency varies; the account history continued growing between samples.

| Read | Original | Optimized | SQL queries |
| --- | ---: | ---: | ---: |
| Capital overview | 12.813 s | 7.326 s | 17 → 10 |
| Invest home | 24.292 s | 13.897 s | 44 → 25 |

Both reads were approximately 43% faster. Remote database round trips remain the main delay: the final samples spent 4.593 s and 13.030 s in SQL. These changes do not make every page instantaneous.

Changes:

- Reuse one locked Capital book across the dashboard and execution overview. Keep balances uncached between requests.
- Memoize schema and seeding checks only within a database transaction, invalidating across commit, rollback and savepoints.
- Reuse broker valuations for Invest holdings; avoid reloading the same instruments, FX and quotes.
- Load independent page requests concurrently; forward the session token without waiting for an extra user lookup. Backend signature/permission checks and layout user verification remain in place.
- Coalesce websocket-triggered page refreshes into 30-second windows, pause hidden tabs, and avoid overlapping refreshes. Live quote delivery remains immediate. Capital keeps its own account polling.
- Move synchronous JWT/JWK verification off the API event loop.
- Background execution cycles no longer build and discard a dashboard response after committing their work.

## Why the paper account had no trades

Read-only inspection found Automatic mode enabled, an active execution heartbeat, and zero orders. Earlier regular-session radar records contained movers without executable quotes or measured liquidity. Several stored quotes dated back to 2 October. The closed-market blocker observed during this audit does not by itself explain the earlier absence of orders.

A direct provider check returned HTTP 200 from Tiingo for three symbols, but every row had a null `lastSaleTimestamp` and null `last`. Those indicative/closing prices correctly cannot fill an order. The bug was treating this empty parsed quote result as provider success, suppressing the FMP fallback. That case now permits fallback, with regression tests. Partial valid Tiingo coverage still avoids an unrestricted fallback for every omitted symbol.

The configured general quote refresh is 600 seconds, while execution accepts quotes no older than 120 seconds. Active pending orders and open positions now receive a dedicated execution-worker REST fallback when a fresh stream observation is unavailable. Pending orders require a later observation than their submission; holdings are refreshed before the age limit. Fetching happens outside account locks. No provider calls are made by this path outside regular trading hours.

Radar names missing an instrument/quote no longer disappear silently through an inner join. The execution response explains the gap, and the UI expands execution blockers when Automatic has no orders or positions.

No trades were manufactured, no entry thresholds were relaxed, and no account reset was performed. A real account fill still needs an open market, a qualifying signal, fresh provider data, and capital capacity. End-to-end order fills and exits are exercised in the disposable PostgreSQL suite; an actual next-session account fill has not yet been observed.

## Validation

- 312 backend unit tests passed.
- 28 disposable PostgreSQL integration tests passed, including fills/exits, account isolation, cash/risk invariants, concurrent execution, migrations, resets, missing-quote diagnostics and the background worker read path.
- Five deterministic frontend refresh scheduler tests passed (`node --test tests/live-refresh.test.mjs`, from `frontend`).
- 25 existing Capital/Invest server-render scenarios passed.
- Frontend lint, TypeScript checks and production build passed.

Both local Celery workers were warm-restarted to load the fixes. Post-restart verification found both ready with no startup exceptions, a successful execution cycle, and a heartbeat 27 seconds old. The account remained in Automatic mode with $10,000 cash and zero orders; the current blocker was the closed US regular session.

## Open-session follow-up — 7 October 2026

At 14:51 UTC the execution heartbeat was current and Automatic mode was enabled, but no orders existed. The market was open; yesterday's closed-session explanation was no longer sufficient.

A live Tiingo response contained current `tngoLast` and `timestamp` fields, while `last` and `lastSaleTimestamp` were null. [Tiingo's IEX documentation](https://www.tiingo.com/documentation/iex) confirms this is its derived reference-price feed; the exchange trade fields require TOPS entitlement. Yesterday's parser correction handled empty results but did not support this valid reference feed. REST now records it as `tiingo_reference`, using its original provider timestamp and matching reference price. This is consistent with the reference-price websocket feed already supported by the simulator. It does not claim an executable exchange bid or offer. Stale, future-dated, missing-timestamp and mismatched-price observations remain blocked. The simulation notice now explicitly discloses reference-price fills.

A second bug grouped 101 names without industry metadata into an artificial industry and labeled them a market-wide event. Unknown classifications now remain unknown and cannot manufacture industry/market breadth. Stale/carried-forward flags no longer contribute to breadth. Known-industry breadth tests continue to pass; no signal, liquidity, price, capital or risk thresholds were lowered.

Quote selection now prioritizes new positive US discoveries meeting the existing price floor ahead of pinned historical names, while preserving watched/held-name priority and the existing provider-call cap. Previously the older working set could continually consume the quote budget.

The new disposable-database test completes a reference-price entry and profit-target exit and reconciles both with the Capital ledger. Current validation: 318 unit tests and 29 PostgreSQL integration tests, including that new round trip.

After the updated workers were loaded, the actual paper account generated an automatic DFNS limit order at 15:00:36 UTC: 78 shares with a $6.33 limit ($493.74 maximum share notional, before fees). At the 15:02 UTC read it was still pending; cash was $10,000 and the trade journal had no fills. A later timestamped reference observation was present. The $6.325 reference plus modeled adverse slippage rounds to $6.34, above the limit, so leaving the order pending was correct. The limit was not raised to manufacture a fill. Both workers reported healthy cycles without exceptions.
