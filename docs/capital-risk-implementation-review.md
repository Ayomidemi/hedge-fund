# Capital implementation review — 8 October 2026

Reviewed the recent Capital execution, statistical risk, profile persistence,
historical-data worker, API, migration and UI changes. The review found additional
defects and corrected them. Passing the previous suite did not establish that
all boundary cases were covered.

## Findings corrected

| Finding | Consequence before the fix | Correction and evidence |
| --- | --- | --- |
| Drawdown checked after a batch of entries | The first fill's costs could cross the drawdown threshold, yet another pending buy could still fill in that cycle. | Recheck drawdown before every pending fill; latch the halt and cancel remaining entries. Regression reproduces the first-fill/second-fill boundary. |
| Returns aligned only by their ending date | A holding missing a bar could contribute a two-session return alongside another holding's one-session return. | Align by both start and end dates for portfolio returns, beta and correlations. A missing-bar regression confirms mismatched intervals are excluded. |
| Sparse volume accepted; zero volume omitted | One observed day could stand in for a liquidity history, and omitting zero-volume days overstated average capacity. | Require at least 15 known observations in the latest 20 bars; retain genuine zeros in averages. Test both existing-holding liquidity and zero-volume sensitivity. |
| Timeout rollback expired the remaining ORM objects | After one provider timeout, accessing the next instrument could raise an asynchronous lazy-load error and stop the batch. Malformed provider data could also terminate the batch. | Snapshot the selected instrument metadata before fetching; roll back and continue after timeout/data errors. A PostgreSQL test forces a timeout and malformed data before two successful requests. |
| Concurrent creation of a shared risk-policy version | Two accounts capturing the same policy for the first time could race into the unique constraint and fail a snapshot request. | Insert with conflict handling, then read the shared version. A barrier forces both test transactions past the initial lookup before either inserts; both finish with the same version ID. |
| Save allowed during settings reload | A delayed GET response could overwrite the displayed profile after a successful save. | Disable selection and saving during reload. The browser test delays the GET and verifies both controls stay disabled until it finishes. |
| Proposed-risk cash used unrounded fees | Statistical checks modeled slightly more cash than the actual rounded reservation. | Use the execution fee function. Regression verifies a $400.40 commitment reserves $0.21 in fees and leaves $9,599.39 from $10,000. |
| Order evidence omitted effective thresholds | Version/profile names alone could not reconstruct the account-specific limits used to approve an order. | Store a copy of the complete resolved policy in each queue/fill risk assessment. Regression checks preservation of the limits. |
| Manual-mode copy hid forced liquidation | The UI claimed all automatic sells stopped even though an already-triggered liquidation continues. | Clarify the exception in status, messages and warnings; show delayed required exits when the worker heartbeat is stale. Execution semantics are unchanged. |

The first five new pure-function cases failed against the previous code before
the fixes. The expanded suite then passed after corrections. Policy version 3
and Risk Centre version 2026.10.3 distinguish these semantics from the previous
implementation. Profile limits themselves are unchanged. No schema migration
is needed for this review's corrections.

## Verification

- **346 unit tests passed**, including the new numerical and fill-boundary cases.
- **36 PostgreSQL integration/migration tests passed** in disposable schemas.
- The actual settings component passed browser interaction tests with a mocked
  API, including save failures, retry, profile changes and slow reloads.
- TypeScript and full frontend ESLint checks passed. The full lint run also
  caught CommonJS-import lint errors in the new browser harness; these were
  corrected and the browser test rerun successfully.
- Eighteen Capital render scenarios passed, including required liquidation in
  Manual mode, delayed required exits, and a flat halted account.
- Original risk probes and synthetic execution scenarios were rerun.
- `git diff --check` passed.

The integration suite also continues to cover concurrent order execution,
idempotent booking, profile persistence, conflicting settings updates, missing
history, preservation of stops/halts/cash, and migration compatibility.

Runtime check: the local API, Redis and both Celery workers were stopped; worker
logs showed clean shutdowns. This review did not restart the stopped app or
change trading mode. The fixes are ready for the next normal development-stack
start; a running policy-version-3 cycle was not verified during this review.

## Scope and practical limits

This is a review of the recent Capital changes, not an assurance that every
feature of the entire product is defect-free. The separate Invest readiness
findings remain documented in `invest-automation-audit.md`; Invest automation
was not enabled or changed here.

The paper engine still uses reference-price simulation, fixed stop/target plans,
and no production partial-fill accounting. Sparse histories can now block
entries more conservatively. Provider coverage, earnings/corporate-action data,
and real execution depth remain modeling limitations. Synthetic scenarios do
not establish trading profitability. Existing live-session execution checks
must still be observed during an open session after the update.
