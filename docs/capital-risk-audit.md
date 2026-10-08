# Capital risk assessment — 7 October 2026

Implementation follow-up: see [Capital risk controls](capital-risk-controls.md)
for fixes, selectable profiles, validation and remaining modeling limits. The
assessment below records the pre-fix findings.

Capital has useful mechanical execution safeguards, but its statistical risk
models are not yet reliable enough to govern automatic allocation. Correctness,
consistent policy, and enforcement should come before more complex models or
higher exposure. This assessment adds a reproducible diagnostic script; it does
not change production code, account settings, balances, or trades.

## Active fund and controls

A database transaction explicitly set to READ ONLY verified the current run.
Its most recent cycle at inspection was 2026-10-07 16:49:06 UTC; the run was
running with one closed and one open order. These are point-in-time counts,
not a performance evaluation.

| Control | Effective automatic policy | Meaning at initial $10,000 NAV |
| --- | --- | --- |
| Position allocation | 5% | Up to $500 including entry costs |
| Planned stop loss budget per trade | 0.5% | Up to $50; position cap usually binds first |
| Concurrent positions | 5 | Approximately $2,500 aggregate initial notional ceiling |
| Minimum cash | 20% | $2,000 floor; position/count caps generally leave much more cash |
| Sector allocation | 20% | $2,000 ceiling |
| Stop / target | 3% / 6% from entry limit | Fixed percentages across eligible instruments |
| Drawdown halt | 5% | About $500 from an initial $10,000 peak; not a guaranteed loss ceiling |
| Simulated execution costs | 10 bps slippage; 5 bps fee per fill | Plus cent rounding |
| Quote / signal age | 120 seconds / 15 minutes | Invalid data prevents execution |
| Entry expiry | 30 minutes | Unfilled orders expire |

The gross ceiling assumes unchanged NAV, no manual holdings, and no price
appreciation. It is an entry constraint, not continuous rebalancing. Whole shares
and fees reduce deployable amounts. For example, the actual sizing function
returns 49 shares at a $10.01 limit, a $9.70 stop and $10.62 target: $490.49 gross
notional. Its modeled stop loss with adverse slippage and fees is approximately
$16.17, rather than the $50 maximum risk budget. A 6% gross gain on $2,500 is
$150 before costs; that arithmetic is not a forecast or a weekly return target.

Existing strengths: pending cash reservations; sizing that includes fees and
modeled stop slippage; sector capacity including pending/manual holdings;
fresh provider timestamps; no fill from the observation that created an order;
limit-price checks; rechecking cash, position notional, sector and planned loss
at fill; gap-sensitive stop exits; flow-adjusted drawdown tracking; locked,
idempotent booking into the shared Capital ledger.

Sources: `backend/app/services/paper_fund/{engine,capital}.py` and
`backend/app/services/market_radar/execution.py`.

## Findings and fixes, in priority order

### 1. Statistical models are advisory to automatic execution — high

`engine.cycle` and `_queue_signals` use quote eligibility, sizing and mechanical
limits. They do not call Risk Centre's volatility, VaR, expected shortfall,
correlation or stress evaluation. `capital.book_fills` records `risk_decision`
as `approve` for the execution policy checks, without a statistical pre-trade
assessment. Manual Capital entries use a separate risk approval path.

Build one shared decision function for proposed holdings, pending commitments,
current cash and marks. Invoke it at queue time and again under the portfolio
lock immediately before filling. Persist policy version, observations, coverage,
results and reason codes. Separate hard blocks, size reductions, warnings and
informational scenarios. Risk-reducing exits must remain available during entry
blocks. Do not simply call today's Risk Centre unchanged: finding 6 would cause
unnecessary review decisions.

### 2. Missing history can look like zero risk — high

`risk_centre._portfolio_returns` skips a ticker when finding common dates if it
has no history, then assigns it zero return in the weighted sum. A two-holding
probe with flat prices for one and no history for the other reports 0% VaR,
0% volatility, a numeric liquidity estimate and no notes. Liquidity similarly
takes the maximum of known values while omitting unknown holdings.

Require coverage of all material positions, including the proposed purchase.
Unknown risk must stay unknown, not become zero. Publish covered NAV, missing
tickers, oldest observation, aligned sample count and tail sample count. An
approved conservative fallback or a clear entry block should govern incomplete
coverage. Preserve exits. Existing tests cover wholly missing history, but not
this partially missing portfolio.

### 3. History quality and statistical conventions need repair — high

`compute_portfolio_market_stats` accepts six-year-old history without a warning;
volatility needs only two returns and correlation/beta only three. Historical
95% VaR requires 20 returns, which leaves only about one tail observation for
expected shortfall. The loader has no as-of cutoff, recency rule, or bounded
lookback. It deduplicates Yahoo/live bars, which is good, but mixing adjusted
and raw closes needs corporate-action validation.

VaR is a signed return quantile but the policy compares its absolute value.
A history with only +5% returns therefore breaches a 4% *loss* threshold.
Define loss-positive VaR/ES consistently, with zero loss for an all-gain tail;
avoid rounding the VaR threshold before selecting the ES tail.

Use completed, adjusted, date-aligned daily observations with explicit as-of
and freshness rules. A proposed initial standard is 252 trading observations;
shorter histories need a visibly lower confidence tier and a separate fallback
policy. Even 252 observations leave only about 12–13 observations in a 5% tail.
Compare historical estimates with a recent-volatility estimate and stress
scenarios. Calibrate these choices using held-out data rather than treating
252 observations as proof of accuracy.

`max_drawdown_pct` in Risk Centre compounds today's weights through historical
returns. This describes a hypothetical constant-weight portfolio, not the
account's realized drawdown. Label it accordingly and show actual account
drawdown from the flow-adjusted equity record separately.

### 4. There are multiple conflicting policies — high

The Capital ledger defaults, Risk Centre's `DEFAULT_POLICY_LIMITS`, and the
automatic engine's `POLICY` differ. Runtime Capital limits are 5% equity, 25%
ETF, 30% sector, 15% minimum cash and no uncovered leverage. Automatic execution
uses 5%, 5%, 20%, and 20% respectively; Risk Centre evaluates static defaults.

`capital_policy` collapses equity and ETF caps into one number. Consequently,
the stock limit restricts ETFs too. It also repeatedly clamps the *previous*
effective policy: after tightening to 5%, changing the configured limit to 8%
still produces 5% for that run. This is a configuration mismatch, not a reason
to automatically increase current allocations.

Resolve a versioned strategy policy and account policy afresh on each change,
retain separate asset-class caps, and show the exact enforced values everywhere.
Existing orders need explicit revalidation when a policy version changes.

### 5. Position-count cap is not repeated at fill — high

`size_order` enforces five active positions, but `process_orders` does not repeat
that check. A deterministic probe adds five manual holdings after queuing a
pending buy; the buy fills, producing six holdings. Fill-time notional/sector/
cash checks alone do not prevent this.

Recheck distinct instrument exposure and pending commitments under the lock,
including manual holdings. Cancel or resize invalidated orders with a concrete
reason. Test concurrent manual additions and multiple pending entries.

### 6. Cash withdrawal stress forces review regardless of market exposure — medium

The default cash-withdrawal scenario subtracts 10% of NAV and `_stress_severity`
classifies that as `reduce`. `_pre_trade_decision` then returns
`reduce_or_review`, even for a cash-only solvent portfolio. A withdrawal is a
capital-flow/liquidity scenario; it should not automatically be treated as a
10% investment loss.

Keep the scenario, but assess available cash and required liquidation rather
than treating the external flow itself as market P&L. Explicitly distinguish
stress scenarios that gate entries from scenarios shown for information.

### 7. Portfolio, liquidity and event risks are under-modeled — next phase

There is no explicit aggregate planned-stop-loss budget, correlation-cluster
limit, daily loss circuit breaker, earnings-event gate, or spread/depth-based
sizing in the automatic path. Sector caps do not capture correlated positions
across sectors. The $500,000 average-dollar-volume entry threshold is only a
coarse filter. Liquidity days assume 10% daily participation; the fill simulator
does not enforce that participation or simulate partial fills and queue priority.

After correctness fixes, add aggregate open-plus-pending risk, daily loss and
correlated-exposure limits. Compare volatility/ATR-based stops and resulting
smaller share counts against today's fixed 3% stops using walk-forward tests.
Never widen an existing stop merely to avoid realizing a loss. Add earnings,
corporate-action and trading-halt data; missing event data must be visible.
Simulate observed spreads, stressed slippage, partial fills and gaps where data
supports them. Keep reference-price simulations explicitly labeled.

Retain the current allocation caps during this work. New numeric budgets should
be tested as candidate configurations, not selected to manufacture more trades
or fit one profitable week.

### 8. Halt and Manual semantics need clearer risk ownership — next phase

Manual mode pauses ordinary automated stops and targets. An already-latched
forced liquidation continues. Fund drawdown includes manual holdings, but forced
exits iterate managed `PaperOrder` positions only; external manual holdings can
remain after the automatic run completes. Fresh quotes and an open regular
session are required for exits; stale data or gaps can take losses beyond 5%.

Distinguish “pause new entries” from “disable automatic exits,” and define which
holdings an account-level liquidation can sell. Preserve the user's current
toggle semantics until deliberately changed. Add stress cases for worker
outages, overnight gaps, stale marks, manual holdings and recovery after a halt.
The SEC explains that stop prices are triggers rather than guaranteed execution
prices, and stop-limit orders can remain unfilled:
[SEC stop-order bulletin](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15).

## Validation and practical sequence

1. Correct data coverage, signs, policy resolution, cash-stress semantics and
   fill-time invariants; add regression tests for each reproduced gap.
2. Integrate the shared decision engine, including proposed holdings and pending
   exposure, and record why every candidate was accepted, resized or blocked.
3. Add aggregate and event risk plus more realistic execution. Cache historical
   analytics by data/policy version outside locks; keep cash/reservation/fill
   checks transactional so better risk controls do not worsen navigation.
4. Replay volatile periods and data failures; use walk-forward evaluation with
   costs and point-in-time inputs. Compare forecast risk with subsequent P&L,
   consistent with the core backtesting principle described by
   [BIS](https://www.bis.org/publications/199601-standards-supervisory-framework-use-of-backtesting-conjunction-internal-models-approach-market-risk-capital-requirements).
   This is methodological guidance, not a claim that bank regulation applies here.
5. Use the first paper week to assess execution reliability, exposure, total
   marked P&L net of fees, drawdown, stale-data time, fill/expiry rates, slippage,
   blocker reasons, and realized versus planned stop losses. Track benchmark
   context and cash deployment. One week can expose operational defects; it is
   not evidence of dependable profitability or well-calibrated tail losses.

Validation performed for this assessment:

- All **318 existing unit tests passed**.
- `backend/audits/capital_risk.py` ran nine deterministic probes: eight reproduced
  gaps, and one demonstrated current sizing. These print evidence; they are not
  assertions that the system is ready, nor fixes to the gaps.
- `git diff --check` passed. No production risk settings or execution behavior
  were changed. Database integration tests were not rerun for this assessment
  because only documentation and an isolated in-memory diagnostic were added.

Reproduce from `backend`: `.venv/bin/python audits/capital_risk.py`.
