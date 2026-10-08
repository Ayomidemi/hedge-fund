# Capital risk controls — implementation, 7 October 2026

Follow-up: [implementation review, 8 October](capital-risk-implementation-review.md)
records further fixes and the policy-version-3 validation results. The activation
details below describe the initial version-2 rollout.

Capital now stores a Low / Medium / High preference in Settings → Capital risk.
Medium is the default. The separate Invest account is unaffected. Profiles
govern risk tolerance, not expected returns.

## Effective limits

These values include this account's existing 5% stock and 25% ETF hard caps.
Settings computes the table from the same resolver used by execution; another
account's stricter hard limits can reduce them further.

| Limit | Low | Medium | High |
| --- | ---: | ---: | ---: |
| Stock position | 3% | 5% | 5% |
| ETF position | 5% | 10% | 20% |
| Concurrent positions | 3 | 5 | 8 |
| Minimum cash | 60% | 20% | 20% |
| Planned loss per trade | 0.25% | 0.5% | 1% |
| Aggregate open/pending planned loss | 0.75% | 1.5% | 3% |
| Daily loss: pause new entries | 1% | 2% | 3% |
| Peak drawdown: halt managed execution | 3% | 5% | 8% |
| Sector exposure | 10% | 20% | 25% |
| Correlated group exposure | 6% | 15% | 20% |
| Annualized portfolio volatility | 20% | 30% | 40% |
| Historical daily 95% loss VaR | 2% | 4% | 5% |
| Historical daily 95% expected shortfall | 3% | 6% | 8% |
| Largest standard market/sector/name stress loss | 3% | 5% | 8% |

The proposed profiles are conservative engineering defaults, not empirically
optimized allocations. Existing limits can bind first: five stocks capped at
5% still imply approximately 25% initial deployment, not 80% deployment just
because the minimum cash setting is 20%. Position gains can move exposure above
an entry cap; this implementation does not continuously rebalance holdings.

All profiles retain whole shares, cash funding, 3% initial stops, 6% targets,
10 bps simulated slippage and 5 bps fees per side. Missing eligible quotes block
fills. Historical volume capacity is limited to 1% of average observed daily
volume; estimated liquidation time is capped at one day at that participation.
This is a capacity filter, not a guarantee of executable liquidity.

## Changes to execution and analytics

- Statistical risk now checks proposed positions, existing holdings, and pending
  buys both before queueing and again before filling. Approved decisions retain
  profile, version, timestamp, metrics, coverage notes and stress loss in order
  evidence; entry trades retain the fill assessment in risk notes.
- Aggregate planned loss includes open and pending plans. Manual holdings with
  no managed stop are conservatively counted at their full value for this budget.
  Distinct instrument count is rechecked at fill.
- Daily loss uses flow-adjusted equity and latches an entry pause for the New
  York calendar day. It does not disable exits. Its first baseline is recorded
  when the control first observes the fund; subsequent day baselines use the
  preceding observed equity. Changing profile cannot clear this latch or an
  existing drawdown halt.
- Correlation groups join positively correlated holdings across sectors at
  correlation >= 0.8. The full group, not merely each pair, must fit its budget.
- Holdings with missing, stale, nonfinite or incomplete adjusted price history
  no longer contribute an assumed zero return. Portfolio risk stays unknown
  and new entries are blocked. Unknown liquidity is not silently dropped.
- Analytics use completed daily bars before the assessment date, bounded to
  the latest 253 observations within 550 calendar days. A minimum of 60 aligned
  returns is required, with the most recent bar within five calendar days;
  coverage notes show the sample count and the 252-return target. Sixty returns
  provide very few tail observations, so these estimates are deliberately
  supplemented by fixed stress and mechanical loss limits.
- Tiingo adjusted history is included alongside Yahoo. A bounded refresh job
  prepares at most four instruments every five minutes on the data worker,
  outside execution locks. Thin histories rotate through the batch rather than
  monopolizing it. Entry-only historical reads are skipped outside an active
  automatic entry session.
- VaR/ES consistently represent losses as positive numbers; an all-gain tail
  has zero loss. Expected-shortfall tail selection happens before rounding.
- Cash-withdrawal stress is assessed for liquidity shortfall rather than
  automatically classifying the withdrawal as an investment loss. Market
  stress remains separate. Historical constant-weight drawdown is explicitly
  distinguished from actual account drawdown.
- Capital's dashboard checks, Risk Centre common limits, settings preview and
  automatic execution resolve the same profile and account ceilings. Stock and
  ETF limits are separate; resolving from the base profile fixes the permanent
  tightening bug. Saved Risk Centre versions include the effective policy hash.

## Changing profiles

`GET /api/paper-fund/risk-settings` returns the saved profile and effective
options. `POST` accepts only `profile` and `expected_profile`, each one of low,
medium or high. The owner is supplied by authenticated Capital access, not the
request body. A stale selection returns 409; unsupported values/fields return
422. Changes take the same portfolio/run locks as execution and are logged.

A successful change cancels pending entries for a fresh assessment and retains
existing cash, holdings, stops, targets, run dates, trading mode and halt state.
Expired/unfilled cancelled plans can be reassessed without creating duplicate
order rows. An entry invalidated below its stop cannot reuse the same signal.
Open-position stops are never widened by changing the profile.

## Verification and activation

- 340 unit tests and 34 PostgreSQL integration/migration tests passed.
- The original eight risk diagnostic gaps now report `gap_present: false`.
- The real React settings component passed browser checks with a mocked API:
  initial selection, all three choices, explicit save, failure preservation,
  retry, updated saved state and the next save's expected profile. No account
  profile was changed by these browser tests.
- Existing 15 Capital UI rendering scenarios passed. TypeScript, changed-file
  ESLint and whitespace checks passed.
- Additive migration `202610070001` was tested on disposable schemas, then
  applied to the verified application database. Automatic review initially
  rejected an unverified database target; after checking the host, schema
  revision and known fund, the verified migration was accepted and applied.
- Workers were restarted. A read-only check confirmed Medium, Automatic,
  policy version 2 and a fresh heartbeat. At 21:09 UTC on October 7, the regular
  US session was closed; the fund had one closed and one open order. This
  confirms activation, not an observed version-2 fill during an open session.

Relevant commands from `backend`:

```sh
.venv/bin/python -m unittest discover -s tests/unit
HF_TEST_DATABASE_URL=postgresql+asyncpg://postgres@127.0.0.1:55439/hedge_audit_test .venv/bin/python -m unittest discover -s tests/integration
.venv/bin/python audits/capital_risk.py
.venv/bin/python audits/capital_execution_scenarios.py
```

From `frontend`, with a local test Chrome on debugging port 9333:

```sh
node scripts/check-capital-risk-ui.cjs
npx tsc --noEmit
```

## Model experiments and remaining practical limits

`audits/capital_execution_scenarios.py` is an isolated synthetic experiment. It
compares fixed-stop sizing with an ATR-derived wider stop using pre-entry bars,
then replays bid-side fills with explicit spreads, gaps, finite capacity and
stale observations. In its fixed fixture, the wider ATR stop reduces size from
49 to 30 shares; a normal stop loses $16.65, whereas a large gap loses $100.40.
A partial exit leaves 39 shares exposed. These are test outcomes, not forecasts.

ATR stops and partial-fill accounting have **not** replaced the running paper
simulator. Choosing a strategy based on these synthetic examples would be
unjustified. Historical walk-forward evaluation with point-in-time signals and
reliable intraday data is still needed before changing the strategy. Earnings
calendars and full corporate-action accounting are not connected; the product's
simulation notice says so. Reference prices do not supply exchange depth or
queue position. Risk-reducing exits remain dependent on valid prices, the worker
and the regular session. Manual mode still pauses ordinary stops/targets, and
automatic liquidation covers managed plans, not externally managed holdings.

For the paper week, use the existing Capital performance and order records to
review marked P&L after fees, cash deployment, drawdown, expiry/fill rates,
blocked candidates, data gaps and realized versus planned losses. New limits
are not evidence of a profitable strategy. Keep the selected profile fixed
during a comparison window and record any change when interpreting results.
