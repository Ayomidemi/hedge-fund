# Radar flow follow-up audit — 14 October 2026

## Assessment

The second review found additional defects in observation merging, stale-data
handling, summaries and scan failure recovery. These are corrected locally with
regression coverage. The discovery → verified quote → historical evidence →
priority → execution eligibility boundary remains intact; the scanner does not
create orders.

This is implementation verification, not evidence of profitable signals or
complete market coverage. The universe, instrument classification and data
coverage work identified in [the foundation audit](radar-foundation-audit.md)
still comes before increasing execution activity. Scheduled workers need to load
these changes and fresh scans need to be observed before operational sign-off.
This review did not restart workers, run production scans or change fund data.

## Corrections

1. **Mixed observations through candidate merging.** A newer incomplete candidate
   could inherit the older return, volume and derived confirmation. Replace the
   observation together and clear statistics that must be recomputed. Older
   observations can contribute discovery provenance, but cannot replace current
   confirmation evidence.
2. **Verified cache ignored after discovery.** A discovery list's receipt time
   and vendor label could prevent a valid cached quote from being used. Compare
   verified observation timestamps, and look up the cache after merging newly
   discovered names. Fresh quote selection still obeys the existing age limits.
3. **Old relative confirmation retained.** Recomputing sector evidence now clears
   prior relative returns before checking benchmark availability and freshness.
4. **Stale observations remained alerts.** Suppress their active flags and scores,
   omit them from alert lists and scan-change lists, and prevent a stale legacy
   priority from reappearing through the overview response.
5. **Stale peers distorted breadth and direction.** Exclude stale, carried and
   missing-return observations from the eligible peer denominator, medians and
   advance/decline counts. Breadth still describes a selected sample; this does
   not solve the broader coverage problem.
6. **Dashboard classifications diverged from scan evidence.** Preserve stored
   classification, use the full scan for fallback classification, and use the
   same deterministic run ordering as execution. Displayed group counts and
   medians continue to describe displayed names. Descriptive flags below the
   attention threshold no longer become alerts when snapshots are read back.
7. **Malformed numeric input.** Reject nonfinite vendor numbers and nonfinite
   statistical evidence. Integer conversion also handles infinity without
   throwing. Incomplete observations remain ineligible for active priority.
8. **Partial writes on failure.** Roll back the entire scan transaction before
   recording a failed run in a fresh transaction. Previously, an application
   failure could commit partially written quotes/snapshots, while a database
   failure left the session unable to record failure at all.
9. **Credentials in vendor error strings.** Discovery errors now expose HTTP
   status or exception type rather than request URLs that may contain API keys.
   Existing historical logs are not rewritten.

## Verification

- Seven initial regression cases reproduced defects before the fixes (nine
  failures including numeric subcases).
- Full backend suite: **369 unit tests and 45 PostgreSQL integration/migration
  tests passed** against an isolated disposable database.
- After the final alert-count correction, all **70 radar unit tests** and the
  affected database overview regression passed again.
- Failure-injection tests cover both application exceptions and an actual SQL
  error after quotes and snapshots have been flushed. They verify rollback,
  recovery of the session, one failed-run record and no orders created.
- Overview tests include tied scan start times, stale legacy priorities, names
  outside the display set and descriptive flags below the attention threshold.
- Existing integration coverage for simultaneous entries, cash reservations,
  risk checks and independent exits passed. No execution thresholds were changed.
- `git diff --check` passed. No frontend source or schema changes were required.

## Remaining checks before execution expansion

Reload the scheduled workers and observe a fresh market-session scan. Confirm
quote coverage, completed-history coverage, exclusion reasons and dashboard
agreement with stored evidence. Then address the verified instrument universe
and reliable history/quote preparation identified in the foundation audit.
One concrete coverage bottleneck remains: `refresh_risk_history` prepares
held instruments and the latest P0/P1 names, with a four-name batch. Other
discovered names do not receive preparation through that job. History coverage
therefore needs its own universe-wide preparation path, independent of already
having a high radar priority.
The October 13 coverage figures in that report are historical diagnostics, not
a measurement of today's running service.
