# Radar foundation audit — 13 October 2026

## Conclusion

The concern is supported by the implementation and observed output. The radar
has both data-integrity defects and limited discovery coverage. Increasing
automatic trade frequency before addressing those foundations would amplify
unreliable inputs. Attention priority is not an expected-return estimate.

This review repaired reproducible integrity defects locally and tested them.
It did not expand the trading mandate, alter account risk limits, place trades,
or restart the scheduled worker. Deployment of these scanner changes is pending.

## What it actually scans

- A curated list of 50 US equities, Nigerian seeds, sector/market ETFs, book and
  watchlist names, retained prior discoveries, and vendor mover lists.
- US discovery takes at most 15 entries from each of three lists: actives,
  gainers and losers. Their union is not an exchange-wide stock screen.
- Quote refresh is capped at 60 US and 12 Nigerian names per scan. Priority
  scheduling is not a guarantee that every catalog name is refreshed fairly.
- A five-minute scan cadence and a nominal 100-name display working set. The
  automatic engine examines P0/P1 snapshots beyond that display subset.
- P0 combines position-risk alerts and extraordinary moves; it does not mean
  a positive investment opportunity. Signals still pass execution gates.

## Read-only observations

The 13:50 UTC scan had 210 snapshots, 74 recorded provider quote timestamps,
38 P0 classifications and no P1 classifications. Many top-ranked names had
identical saturated scores and no measured volume ratio or verified timestamp.
A recorded timestamp alone does not establish freshness or executable liquidity.

Two stored scans were re-evaluated without writing account or radar data:

| Diagnostic | 13:55 UTC scan | 14:00 UTC scan |
| --- | ---: | ---: |
| Snapshot names | 210 | 211 |
| Stored P0 count | 36 | 38 |
| Replayed P0 count | 3 | 6 |
| Verified-timestamp, current price/return observations | 45 | 46 |
| Adequate current adjusted-return baseline | 13 | 17 |

The second scan had 110 protected working-set names. Its recorded current
portfolio/watchlist/queue flags and pulse identities justified 25 protected
names. Reconstructing current membership and applying the repaired selection
produced a 100-name working set.

These are diagnostics using stored observations and the currently available
historical database, restricted to completed dates before the scan. They are
not exact point-in-time backtests: later backfills/revisions can exist, and
fields already mixed in the original snapshot cannot always be reconstructed.
A reduced P0 count is not evidence of improved investment returns.

## Reproduced defects and corrections

1. **Mixed historical observations.** Multiple providers' rows for the same
   date, today's partial marks and future-dated rows could enter a baseline.
   Now use one completed Tiingo/Yahoo daily observation per date, with Tiingo
   taking precedence. Intraday/live marks are excluded.
2. **Unadjusted historical returns.** Splits could look like historical price
   shocks. Returns now require finite positive adjusted closes. Missing adjusted
   observations produce a gap rather than a raw-price substitute.
3. **Tiny samples.** Three bars could yield a z-score over 1,000 in a regression
   fixture. Require at least 20 completed adjusted returns and a recent final
   bar before computing return anomalies. This is a minimum evidence gate,
   not a calibrated confidence level; execution's separate 60-return risk
   requirement remains in place.
4. **Invented current movement.** A missing session return could be filled with
   the most recent historical daily return. That fallback was removed.
5. **Misleading liquidity baseline.** Zero-volume days were excluded and average
   dollar volume used today's price. Include known zero-volume days and average
   each historical close multiplied by that day's volume. Record sample counts
   and the daily-volume comparison basis.
6. **Discovery confused with confirmation.** Most-active-list membership became
   an `unusual_volume` flag despite missing relative-volume measurements. Store
   discovery-list provenance separately; measured flags are recalculated.
7. **Old/future quotes admitted.** A same-day quote could bypass the radar cache
   age limit, and future timestamps passed the age check. Both are now rejected.
8. **Observation fields mixed across time.** Older incoming quotes could replace
   newer prices. New quotes could inherit an old return or volume. Preserve time
   ordering and use fields from the new observation, deriving its return only
   when its own previous-close value is available.
9. **Unverified/stale observations assigned active priority.** Store explicit
   observation quality and withhold active P0/P1/P2/P3 classification from
   unverified, stale, incomplete or carried-forward observations. Displaying a
   discovery is still possible; it is not an active trading signal.
10. **Stale benchmark confirmation.** Exclude stale/carried-forward benchmarks
    and skip relative-return comparisons when observation times differ by over
    two minutes. The benchmark comparison remains a simple return difference.
11. **Permanent working-set seats.** Prior membership took precedence over new
    anomalies. Ordinary pinned names now compete on current score; ties may
    retain continuity. Current protected names remain visible.
12. **Protected membership never cleared.** Retired book/watchlist names retained
    `always_watched`, including through copied snapshots. Synchronize book
    protection with current membership and prevent prior snapshots restoring it.
13. **Cross-session scan lurches.** Yesterday's daily percentage return was
    compared with today's as though they shared a baseline. Record a session
    comparison gap instead. Sparkline dates use the scan's supplied date.

Each scan now records coverage notes. Observations carry method version 2 and
quality/baseline evidence so missing coverage can be distinguished from quiet
price action. Historical snapshots are not rewritten.

## Remaining design work, in priority order

1. **Define and maintain the actual universe.** Provider-backed instrument
   identities, listing status, security type, corporate actions and explicit
   leveraged/inverse-product eligibility. The current ticker-prefix heuristic
   for ETF discovery is not verified instrument classification.
2. **Build coverage before scoring.** Pre-session history preparation, current
   quotes, bounded retries and fair rotation through supported names. NG names
   without eligible completed daily history now show the gap; they need their
   own validated historical feed rather than fabricated statistics.
3. **Separate evidence dimensions.** Direction, freshness, data completeness,
   abnormal movement, holding-risk urgency and entry suitability should be
   distinct. Missing dimensions currently change the weighted-score denominator;
   scores are not calibrated or directly comparable confidence estimates.
4. **Improve comparisons.** Current volume is compared with completed full-day
   volume, not historical volume at the same time of day. Sector returns are
   subtracted without beta adjustment. Breadth describes a selected monitored
   sample, with data gaps, not the full industry or market. Proper intraday
   baselines, coverage denominators and corporate-action handling are required.
5. **Validate detection before investing.** Measure data coverage, stale rates,
   missed eligible names, stability across rescans and sensitivity to source
   outages. Use timestamped replay with retained inputs. Then separately test
   whether particular detections predict returns after realistic costs.

Correcting these defects may reduce visible high-priority signals and trades.
Missing coverage must be repaired rather than compensated for by weaker gates.

## Verification

- The first 11 added integrity regressions all failed before corrections.
- 360 unit tests and 43 disposable PostgreSQL integration/migration tests passed.
- Database tests cover daily-bar deduplication/filtering, retired protected
  membership, and complete scan persistence with unverified observations withheld
  from active priority and no automatic orders created by the scanner.
- An existing pause/resume test used wall-clock time against an October 2 fixture;
  it failed once that review period expired. Its intended test clock is now fixed.
- `git diff --check` passed. No frontend source changes were made.

Re-run the read-only diagnostic from `backend` with:

```sh
.venv/bin/python -m audits.radar_integrity
```
