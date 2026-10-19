# Capital performance audit — 16 October 2026

## Conclusion

The reported approximately $75 is a real **paper-account accounting gain**, but it is not evidence of a continuously operating strategy earning $75 each week. The account has deployed little capital, execution has substantial recording gaps, and the profit depends on two trades in a misclassified leveraged inverse ETF. Increasing position sizes is not the first fix.

Evidence was captured at **16 October 2026, 15:02:07 UTC / 16:02:07 WAT**, in one PostgreSQL `REPEATABLE READ, READ ONLY` transaction. The account was in Automatic mode with High risk selected. No account settings, orders, balances, workers or provider data were changed. Figures below use the account's saved marks at capture, not a refreshed live valuation.

## What the $75 actually represents

| Metric | Captured value |
| --- | ---: |
| Net contributions | $10,000.00 |
| Cash | $9,576.31 |
| Open BMBL position, 84 shares | $499.38 |
| Total account equity | $10,075.69 |
| Cumulative net profit | **$75.69 / 0.7569%** |
| Realized profit, 15 completed trades | $76.36 |
| Unrealized result, including remaining entry fee | −$0.67 |
| Fees already included | $7.77 |
| Winners / losers | 5 / 10 |
| Total winning / losing closed-trade P/L | +$280.30 / −$203.94 |
| Closed-trade profit factor | 1.37 |

All 31 filled trade records reconcile to their automatic order plans: 16 buys, 15 sells, matching quantities, prices and fees, with unique intent keys. Reconstructed cash equals the cash ledger, and reconstructed remaining quantities equal the BMBL position. No missing debit or duplicated fill was found in this snapshot.

The UI correctly labels this P/L **All time**. It spans two execution reviews:

- First review: began 5 October; scheduled to end 12 October; actually completed 13 October. Three closed trades earned **$17.78**.
- Current review: began 13 October; scheduled to end 20 October. Twelve closed trades earned **$58.58**; the open position contributes −$0.67, making this review's gain **$57.91**, about **0.5781%** of its $10,017.78 opening equity.

A precise rolling-week return cannot be established from saved equity snapshots: the seven-day starting boundary falls inside a multi-day recording gap. Carrying the 8 October mark forward into 9 October would misrepresent a measured weekly opening value. The account contains no additional contributions or withdrawals during these reviews.

## Findings, in implementation priority order

### 1. Execution was not continuously recorded during market hours

Snapshots should be written at least every five minutes while cycles complete. There are none between **8 October 21:37:58 UTC and 13 October 13:45:46 UTC**, spanning all of the 9 and 12 October regular sessions and the opening of 13 October: approximately **13.26 market hours**. Radar records are also absent for those two full sessions in the captured seven-day window.

Other material gaps include 14 October 16:29:59–21:21:32 UTC, encompassing **3.50 market hours**, and substantial gaps on 15 October. These show missing successful cycle/snapshot coverage; they do not, by themselves, distinguish a sleeping host, paused process, failed cycle or database outage. They are not a precise uptime measurement.

SOXS remained open across the largest gap. Its first trade was eventually closed on 13 October for `review_period_ended`, after the review had expired on 12 October. It earned $68.64, but we cannot assume the same exit or return would have occurred with uninterrupted stop/target monitoring. Recorded maximum drawdown, approximately 0.95% for the current review, also cannot capture unobserved intraday losses.

At capture, the execution heartbeat was current (15:01:31 UTC). A subsequent read-only Celery inspection found both the data and execution workers responding on the local MacBook host, with the history and execution tasks registered. This establishes present activity, not historical uptime or the cause of the gaps.

**Fix:** run execution, scheduling and data preparation on a continuously available host; persist cycle outcomes and durations; alert on missed market-hour heartbeats and stale holding quotes. A weekly report must show coverage and stale marks, not just P/L. Do not “repair” missing historical fills by inventing trades.

### 2. Profit depends on leveraged inverse products that have incorrect metadata

The two SOXS trades contributed **+$145.86**. All other closed trades together contributed **−$69.50**. Including the remaining BMBL loss, the account's arithmetic result excluding SOXS is **−$70.17**. This is attribution, not a simulated counterfactual strategy: removing SOXS would also alter available capital, risk and subsequent decisions.

SOXS is stored as `asset_class="equity"`, with no sector or industry. Its issuer describes it as a daily **−3× semiconductor ETF**, with risks associated with daily leveraged/inverse exposure. [Direxion product documentation](https://www.direxion.com/product/daily-semiconductor-bull-bear-3x-etfs).

BMNZ is also stored as an ordinary equity, although its stored name identifies a daily 2× short ETF. Overall, **12 of the 13 traded instruments have no sector or industry**. Position sizing groups missing sectors together; this is a conservative unknown-sector bucket, not valid knowledge of their economic exposures. A no-borrowing limit does not eliminate leverage embedded inside an ETF.

**Fix:** establish verified instrument classification and explicit leveraged/inverse-product eligibility before scaling. Model product-specific risk and holding-period rules. Do not simply relabel SOXS as an ETF and unintentionally move it from the current 5% stock cap to a 20% ETF allowance. Correct metadata and eligibility policy together.

### 3. Closed tickers cannot be traded again during the same review

`_queue_signals` in `backend/app/services/paper_fund/engine.py` includes closed orders in `seen`. Only never-filled cancelled/expired orders are retryable. The database also permits only one order lifecycle per run/instrument.

This is a hardcoded **one completed trade per ticker per review** restriction, independent of available cash and whether the radar finds a fresh signal. The skip is silent, so the generic “no new signal passes” message does not expose it.

In today's captured scans, **33 observations passed the stored signal gates; all were DFNS**, which had already closed on 14 October. Those observations could not produce another order under the current rule. Across the observed week, 154 signal-screen passes occurred after a same-review close, across 11 symbols. These are repeated observations, not 153 independent opportunities or proven missed profits; historical quote, portfolio-risk and fill eligibility were not replayed.

**Fix:** make re-entry an explicit strategy policy. If allowed, require a new signal identity, cooldown, renewed confirmation, per-symbol daily loss/turnover limits, and current risk checks. Support multiple immutable trade lifecycles per ticker with distinct intent keys. Preserve duplicate-order protection and make re-entry exclusions visible. Do not remove the guard without replacement controls.

### 4. The fund uses only a small fraction of its capital

For the exact seven-day window ending at capture, integrating filled trade events over **32.5 US regular-session hours** gives:

| Deployment measure | Result |
| --- | ---: |
| Average acquisition cost of held shares | **$780.40**, or 7.80% of initial capital |
| Average cash reconstructed from fills and fees | **$9,206.50** |
| Maximum acquisition cost held after a fill | $2,434.84 |
| Maximum simultaneous holdings | **5** |
| Current cash as a share of saved equity | **95.04%** |

The acquisition-cost measure is not time-weighted market value or a return on invested capital. It remains reconstructable despite missing valuation snapshots because the filled trade ledger is available. During the current review alone, average acquisition cost held was $955.55.

High risk specifies a 15% stock cap, but the account's active `max_single_equity_position_pct=5` overrides it. Entries therefore remain around $500. The effective settings allow eight positions, retain 20% cash, and cap a sector at 25%. Eight stocks sized at the 5% cap would initially deploy roughly 40% before other constraints; the missing-sector bucket can constrain deployment further.

The nominal 1% per-trade risk allowance does not mean $100 is being risked on every entry. A $500 position with a planned 3% stop has about $15 of price risk before modeled costs. Position-size ceilings bind first. Conversely, gaps can exceed planned losses: JLHL lost $45.60 on its roughly $492 entry.

**Fix:** show the effective risk limits, their overriding account rules, actual deployment, and why cash is idle. Decide whether the current 5% ceiling is intentional only after reliability and product-risk fixes. The evidence does not justify automatically raising it. Multiple positions already execute concurrently; a one-position restriction is not the problem.

### 5. Most radar priority observations are unsuitable for this long-entry strategy

The captured regular-session priority observations, using the current signal rules and the data saved with each scan, split as follows:

| First signal-screen outcome | Observations |
| --- | ---: |
| Falling/directionless price | 1,172 |
| Price below $5 | 664 |
| Missing/insufficient measured dollar liquidity | 610 |
| Missing volume/sector-relative confirmation | 48 |
| Positive move too weak | 45 |
| Signal older than allowed/future-dated | 34 |
| Market-wide move only | 4 |
| Carried/stale observation | 1 |
| Passed stored signal gates | **430 across 17 symbols** |
| Total | **3,008** |

These are repeated snapshots, not independent signals. The diagnostic supplies a local synthetic matching quote solely to isolate stored signal gates. It does **not** demonstrate that historical executable quotes, capacity, risk checks or fill conditions passed. This synthetic input is never persisted or sent to the execution engine.

Sixteen of those 17 names have a plan in the current review: 13 filled (12 closed, one open), three remain expired in the retained record. LOFD has no order; the absence of historical decision logs prevents a reliable explanation. This does not show hundreds of ready trades being ignored.

**Fix:** add a separate strategy-eligible discovery/ranking lane using verified liquid instruments and prepared history, while retaining a broader risk/activity radar. Validate entry quality and persistence on unseen data. Recheck signal confirmation at fill, not only quote validity and portfolio risk: a pending momentum order can otherwise fill during a retreat toward its stop. Do not lower the liquidity/price/freshness gates merely to create more trades.

### 6. History preparation and decision evidence are not sufficient for diagnosis

The latest recorded history-preparation attempt was **15 October 18:16:27 UTC**, about 20 hours 46 minutes before capture, despite current radar activity. There are 599 preparation records: 420 labeled ready, 102 partial, 62 pending, 11 retry and four preparing. All 420 ready records have last-bar dates of 13 or 14 October, earlier than the latest completed session, 15 October. “Ready” is therefore a saved past status, not current freshness. This does not prove every underlying price series is stale: other ingestion paths may update bars without updating preparation records.

The automatic task is registered, so missing registration is not the explanation established by this audit. Investigate schedule delivery, worker contention, errors, lease recovery and task completion before assuming the preparation queue is healthy.

The current run stores only the latest blockers (at most 30). Retried orders overwrite the earlier attempt and retain only one `previous_attempt`. Exact historical rejection rates, retries, missed fills and the cause of every idle period therefore cannot be reconstructed. Current blockers must not be presented as the entire week's causes.

**Fix:** persist structured per-cycle funnel counts and reason codes, immutable order attempts, relevant quote/signal versions, task heartbeats and preparation freshness. This is needed for performance tuning as well as trading safety.

## Benchmark and interpretation limits

SPY/QQQ completed provider bars in the captured database extend only through 14 October. Later `live` rows are intraday marks and cannot be substituted for official closing observations. Combined with the missing account valuations, this prevents a trustworthy same-window weekly benchmark comparison. This audit makes no alpha claim and does not annualize the observed return.

The observed trade sample is small and combines policy versions 1 and 3, implementation changes and execution gaps. The 33.3% win rate and 1.37 profit factor are descriptive, not a validated expectation. Simulated fees/slippage are included; an order book, depth, partial fills, corporate actions and reliably observed intraday stop paths are not fully represented.

## Recommended next work

1. **Reliability and instrument eligibility:** continuous worker hosting/alerts, history-job diagnosis, verified product/sector classification and leveraged-product controls.
2. **Explain and measure decisions:** immutable attempts and rejection history; weekly flow-adjusted reporting with coverage, deployment, costs and realized/unrealized attribution.
3. **Repair strategy restrictions deliberately:** controlled re-entry and fresh signal confirmation at fill; show effective account limits rather than just the High label.
4. **Evaluate strategy quality:** prepare a verified liquid universe, test momentum persistence/entry timing, and run an uninterrupted paper observation period before comparing allocation changes. Increase exposure only if the evidence supports it.

No settings were increased, funds reset, trades placed, modes changed or workers restarted during this audit.

## Reproduction and validation

- `backend/audits/capital_week.py` captures account-scoped evidence using a database-enforced read-only transaction, with statement timeouts and a private local output file. It does not call account services that could seed or mutate state. Raw financial evidence was kept outside the repository.
- `backend/audits/capital_week_metrics.py` calculates deployment, recorded coverage gaps and the signal-only diagnostic offline.
- **381 backend unit tests passed**, including seven new deterministic audit tests covering market-hour integration, concurrent holdings, partial-sale cost basis, pre-existing holdings, planned/future trades, incomplete ledgers and post-close repeat signals.
- Independent reconciliation of the captured 31 fills, cash ledger, fees, unique intent keys and remaining quantities passed.
