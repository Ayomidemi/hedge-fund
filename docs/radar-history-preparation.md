# Radar history preparation

History is prepared independently of radar priority. The existing five-minute
`paper_fund.refresh_risk_history` job now maintains `radar_history_preparation`,
a durable queue shared by supported USD equities and ETFs.

## Discovery to scoring

1. Select active US catalog names, US discoveries from completed scans in the
   preceding 14 days, and open holdings. P0/P1, display working-set membership,
   a current quote and an existing instrument row are not prerequisites for
   history preparation. Existing instrument metadata takes precedence.
2. Check completed Tiingo/Yahoo daily history using radar's Tiingo-first
   precedence. Duplicate dates, invalid prices and today's/future bars cannot
   satisfy preparation coverage.
3. Prepare at most four names per run. Reserve one holding slot and give the
   remaining slots to discoveries when available. Within each group, names
   never attempted go first, then the oldest persisted attempt. Worker restarts
   or a changing universe do not reset rotation.
4. Download up to 550 calendar days with a 12-second per-name deadline. Store
   raw prices separately from adjusted prices; validate dates and volumes.
   Only selected names need instrument rows. Creating one supplies a data
   identity, not a verified security classification or executable quote.
5. Later radar scans use the saved history. Their current-quote, sample-size,
   priority and execution checks remain in force. Preparation never creates
   an order, changes a balance or lowers an entry/risk threshold.

## Progress and retries

The queue records last seen, last attempted, next attempt, status, usable bar
count, latest usable date, consecutive failures and a sanitized error type.

- `pending`: eligible and awaiting its turn.
- `preparing`: attempt recorded before network I/O; a 15-minute lease permits
  retry after worker interruption.
- `ready`: at least 253 usable daily observations, 20 known-volume dates and
  coverage through the previous exchange session. Recheck after six hours.
- `partial`: a successful download still falls short of that preparation
  target. Retry after 12 hours; this avoids repeatedly downloading short IPO
  histories. Radar can already use a shorter history if its own gates pass.
- `retry`: no usable download or an exception. Start with a 30-minute delay,
  doubling up to 24 hours. Other names keep their turns.

Each attempt and result is committed separately. The data worker's existing
database job lock prevents overlapping scheduled preparation runs. Execution
runs on its separate worker and does not wait for these downloads.

The existing verified US session calendar determines the previous session.
This job does not provide Nigerian historical data or establish leveraged ETF
eligibility. A healthy preparation status is not an expected-return estimate
or permission to trade.

## Deployment and verification

Apply migration `202610140001` before restarting the data worker. The schedule
and four-name vendor budget are unchanged. Queue and historical bars begin
filling gradually; the full universe is not prepared in one cycle.

Regression coverage includes unranked discoveries without instrument rows,
catalog names, bounded batches across fresh worker sessions, timeout recovery,
retry delays, short-history progress into radar scoring, provider precedence,
raw/adjusted prices, malformed volume, duplicate/future dates, and migration
compatibility. Full verification: 373 unit tests and 49 PostgreSQL
integration/migration tests.

Activated on 14 October 2026: migration applied to the app database and the data
worker/scheduler reloaded. The first bounded worker run completed in 58 seconds,
found 502 eligible names, saved 1,508 daily bars for four names (377 each), and
left four ready / 498 pending. These counts describe that initial run, not a
promise that every remaining name has sufficient provider history.

The replacement data worker runs in the background; its log is
`/private/tmp/hedge-data-worker-history.log`. `scripts/stop-backend.sh` stops it
along with the rest of the local backend. The API and execution worker were not
restarted for this change.

## Performance follow-up — 14 October 2026

The initial 58-second run was a functional check, not a completed performance
audit. The follow-up found unnecessary snapshot payloads and repeated work:

- Discovery selection now fetches identity fields, avoiding evidence JSON and
  sparklines when sorting/reading two weeks of snapshots.
- History coverage is queried only for names whose preparation/retry time is
  due. A regression verifies zero history-table queries when every name is
  ready or waiting on a retry delay.
- Existing queue rows update their last-seen timestamp at most hourly instead
  of rewriting every eligible row on every five-minute cycle.
- A 90-second asynchronous deadline covers the history job, including selection
  and database work, in addition to its per-download timeout. Session and job
  lock contexts unwind on cancellation; ordinary cleanup can add time beyond
  the deadline. Execution retains its separate worker. Radar/news still share
  the data worker and can wait while a preparation batch runs.
- Logs now include due counts, selection time and total time.

An alternating read-only comparison on the app database returned 502 names in
both versions. Discovery query medians over three samples each were **5.541s
before / 2.244s after**. Samples were 7.478/5.152/5.541s and
3.398/2.028/2.244s respectively. This measures that query, not page-navigation
latency, vendor-download performance or a sustained load-test percentile.

Verification after these changes: **374 unit tests and 49 PostgreSQL integration
and migration tests passed**, including worker timeout cleanup. The bounded
four-name batch remains a throughput limitation: 502 initially unprepared names
would need about 10.5 hours at four successful names per five-minute cycle,
before retries or additional discoveries. This preserves the current API budget;
increasing throughput requires separate capacity/rate-limit planning.

After reloading the data worker, the first optimized batch reported 502 eligible
names, 494 due, four attempted and 1,483 bars saved. Selection took 11.867s and
the preparation service took 41.548s. This includes other database operations
and vendor work; it is a different batch from the original 58-second check and
is not a controlled end-to-end speedup comparison.
