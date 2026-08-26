"use client";

import { useMemo, useState, type ReactNode } from "react";
import { inputControlClassName } from "@/components/ui/form-styles";
import { Modal } from "@/components/ui/Modal";
import {
  deleteReportSnapshot,
  getReportSnapshot,
  getReportOverview,
  saveReportSnapshot,
  updateReportSnapshotTitle,
  type AttributionBucket,
  type AttributionRealizedEvent,
  type AttributionReport,
  type AttributionRow,
  type MonthlyReport,
  type MonthlyReportAttributionRow,
  type ReportCenterView,
  type ReportCompactSection,
  type ReportKind,
  type ReportQueryParams,
  type ReportSnapshot,
} from "@/lib/api";

type ReportsCenterProps = {
  initialReport: MonthlyReport | null;
  initialSnapshots: ReportSnapshot[];
  initialView: ReportCenterView;
  isUnavailable: boolean;
};

const currency = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 2,
  style: "currency",
});

const percentFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const reportKindOptions: { label: string; value: ReportKind }[] = [
  { label: "Daily", value: "daily" },
  { label: "Weekly", value: "weekly" },
  { label: "Monthly", value: "monthly" },
  { label: "Quarterly", value: "quarterly" },
  { label: "Annual", value: "annual" },
];
const reportViewOptions: { label: string; value: ReportCenterView }[] = [
  { label: "Overview", value: "overview" },
  { label: "Attribution", value: "attribution" },
  { label: "Research", value: "research" },
  { label: "Archive", value: "archive" },
];
const monthOptions = buildMonthOptions();
const yearOptions = buildYearOptions();
const quarterOptions = [
  { label: "Q1", value: "1" },
  { label: "Q2", value: "2" },
  { label: "Q3", value: "3" },
  { label: "Q4", value: "4" },
];
const whiteButtonClassName =
  "inline-flex h-10 items-center justify-center rounded-lg border border-zinc-200 bg-white px-4 text-sm font-medium text-zinc-800 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-200 dark:bg-white dark:text-zinc-800 dark:hover:bg-zinc-50";

export function ReportsCenter({
  initialReport,
  initialSnapshots,
  initialView,
  isUnavailable,
}: ReportsCenterProps) {
  const [report, setReport] = useState(initialReport);
  const [snapshots, setSnapshots] = useState(initialSnapshots);
  const [activeView, setActiveView] = useState<ReportCenterView>(initialView);
  const [selectedKind, setSelectedKind] = useState<ReportKind>(
    initialReport?.report_kind ?? "monthly",
  );
  const [selectedMonth, setSelectedMonth] = useState(
    initialReport ? monthInputValue(initialReport.period_start) : currentMonthValue(),
  );
  const [selectedYear, setSelectedYear] = useState(
    initialReport
      ? String(parseDate(initialReport.period_start).getFullYear())
      : String(new Date().getFullYear()),
  );
  const [selectedQuarter, setSelectedQuarter] = useState(
    initialReport
      ? String(quarterFromDate(initialReport.period_start))
      : String(currentQuarter()),
  );
  const [selectedAsOf, setSelectedAsOf] = useState(
    initialReport?.period_start ?? currentDateValue(),
  );
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [archiveAction, setArchiveAction] = useState<string | null>(null);
  const [selectedSnapshot, setSelectedSnapshot] = useState<ReportSnapshot | null>(null);
  const [snapshotTitle, setSnapshotTitle] = useState("");
  const [error, setError] = useState<string | null>(
    isUnavailable ? "Report could not be loaded. Sign in again or refresh." : null,
  );

  const summaryMetrics = useMemo(() => {
    if (!report) return [];
    return [
      { label: "NAV", value: money(report.nav), tone: "neutral" },
      {
        label: "Period P/L",
        value: report.attribution ? money(report.attribution.net_pnl) : "-",
        tone: tone(report.attribution?.net_pnl),
      },
      {
        label: "Period Return",
        value: report.attribution
          ? pct(report.attribution.total_return_pct)
          : "-",
        tone: tone(report.attribution?.total_return_pct),
      },
      {
        label: "Cumulative",
        value: report.cumulative_return_pct ? pct(report.cumulative_return_pct) : "-",
        tone: tone(report.cumulative_return_pct),
      },
      {
        label: "Benchmark",
        value: report.benchmark_summary?.period_return_pct
          ? pct(report.benchmark_summary.period_return_pct)
          : "-",
        tone: tone(report.benchmark_summary?.period_return_pct),
      },
      {
        label: "Risk Warnings",
        value: String(report.risk_warning_count),
        tone: report.risk_warning_count > 0 ? "risk" : "neutral",
      },
    ];
  }, [report]);

  const compactSections = report
    ? [
        report.ai_overview ?? buildClientAiOverview(report),
        report.portfolio_positioning,
        report.market_commentary,
        report.strategy_changes,
        report.research_pipeline,
      ]
    : [];

  async function handleLoad() {
    setLoading(true);
    setError(null);
    try {
      const next = await getReportOverview(currentParams());
      setReport(next);
      syncControls(next);
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : "Report could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }

  async function handleSaveSnapshot() {
    if (!report) return;
    setSaving(true);
    setError(null);
    try {
      const saved = await saveReportSnapshot(currentParams());
      setSnapshots((current) => [saved, ...current.filter((item) => item.id !== saved.id)]);
      if (saved.payload) {
        setReport(saved.payload);
        syncControls(saved.payload);
      }
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? saveError.message
          : "Report snapshot could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  }

  function currentParams(): ReportQueryParams {
    if (selectedKind === "daily") {
      return { kind: selectedKind, as_of: selectedAsOf };
    }
    if (selectedKind === "weekly") {
      return { kind: selectedKind, as_of: selectedAsOf };
    }
    if (selectedKind === "monthly") {
      const [year, month] = selectedMonth.split("-").map(Number);
      return { kind: selectedKind, year, month };
    }
    if (selectedKind === "quarterly") {
      return {
        kind: selectedKind,
        quarter: Number(selectedQuarter),
        year: Number(selectedYear),
      };
    }
    return { kind: selectedKind, year: Number(selectedYear) };
  }

  function syncControls(next: MonthlyReport) {
    setSelectedKind(next.report_kind);
    setSelectedMonth(monthInputValue(next.period_start));
    setSelectedYear(String(parseDate(next.period_start).getFullYear()));
    setSelectedQuarter(String(quarterFromDate(next.period_start)));
    setSelectedAsOf(next.period_start);
  }

  function handleKindChange(nextKind: ReportKind) {
    setSelectedKind(nextKind);
    if (nextKind === "daily" || nextKind === "weekly") {
      setSelectedAsOf(currentDateValue());
    } else if (nextKind === "monthly") {
      setSelectedMonth(currentMonthValue());
    } else if (nextKind === "quarterly") {
      setSelectedQuarter(String(currentQuarter()));
      setSelectedYear(String(new Date().getFullYear()));
    } else {
      setSelectedYear(String(new Date().getFullYear()));
    }
  }

  function handleExport() {
    if (!report) return;
    printReport(report);
  }

  async function resolveSnapshot(snapshot: ReportSnapshot) {
    if (snapshot.payload) return snapshot;
    return getReportSnapshot(snapshot.id);
  }

  async function handleSnapshotOpen(snapshot: ReportSnapshot) {
    setArchiveAction(`open:${snapshot.id}`);
    setError(null);
    try {
      const detail = await resolveSnapshot(snapshot);
      if (!detail.payload) {
        setError("Saved report payload is not available for this snapshot.");
        return;
      }
      setReport(detail.payload);
      syncControls(detail.payload);
      setSelectedSnapshot(null);
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Saved report could not be opened.",
      );
    } finally {
      setArchiveAction(null);
    }
  }

  async function handleSnapshotPreview(snapshot: ReportSnapshot) {
    setArchiveAction(`preview:${snapshot.id}`);
    setError(null);
    try {
      const detail = await resolveSnapshot(snapshot);
      setSelectedSnapshot(detail);
      setSnapshotTitle(detail.title);
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Saved report could not be loaded.",
      );
    } finally {
      setArchiveAction(null);
    }
  }

  async function handleSnapshotRename() {
    if (!selectedSnapshot) return;
    const nextTitle = snapshotTitle.trim();
    if (!nextTitle) return;
    setArchiveAction(`rename:${selectedSnapshot.id}`);
    setError(null);
    try {
      const updated = await updateReportSnapshotTitle(selectedSnapshot.id, nextTitle);
      setSelectedSnapshot(updated);
      setSnapshotTitle(updated.title);
      setSnapshots((current) =>
        current.map((item) => (item.id === updated.id ? { ...item, ...updated } : item)),
      );
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Saved report could not be renamed.",
      );
    } finally {
      setArchiveAction(null);
    }
  }

  async function handleSnapshotDelete(snapshot: ReportSnapshot) {
    setArchiveAction(`delete:${snapshot.id}`);
    setError(null);
    try {
      await deleteReportSnapshot(snapshot.id);
      setSnapshots((current) => current.filter((item) => item.id !== snapshot.id));
      if (selectedSnapshot?.id === snapshot.id) {
        setSelectedSnapshot(null);
      }
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Saved report could not be deleted.",
      );
    } finally {
      setArchiveAction(null);
    }
  }

  async function handleSnapshotExport(snapshot: ReportSnapshot) {
    setArchiveAction(`export:${snapshot.id}`);
    setError(null);
    try {
      const detail = await resolveSnapshot(snapshot);
      if (!detail.payload) {
        setError("Saved report payload is not available for this snapshot.");
        return;
      }
      printReport(detail.payload);
    } catch (snapshotError) {
      setError(
        snapshotError instanceof Error
          ? snapshotError.message
          : "Saved report could not be exported.",
      );
    } finally {
      setArchiveAction(null);
    }
  }

  function handleViewChange(nextView: ReportCenterView) {
    setActiveView(nextView);
    const url = new URL(window.location.href);
    if (nextView === "overview") {
      url.searchParams.delete("view");
    } else {
      url.searchParams.set("view", nextView);
    }
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }

  if (!report) {
    return (
      <section className="mx-auto max-w-[1200px] rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <datalist id="report-month-options">
          {monthOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </datalist>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Reports
        </p>
        <h2 className="mt-2 text-xl font-semibold">
          {error ? "Report could not be loaded yet" : "Report pending"}
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          {error ?? "The report is ready once portfolio data is available."}
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <select
            value={selectedKind}
            onChange={(event) => handleKindChange(event.target.value as ReportKind)}
            className={`${inputControlClassName} h-10 w-[134px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
            aria-label="Report type"
          >
            {reportKindOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <PeriodControls
            selectedAsOf={selectedAsOf}
            selectedKind={selectedKind}
            selectedMonth={selectedMonth}
            selectedQuarter={selectedQuarter}
            selectedYear={selectedYear}
            setSelectedAsOf={setSelectedAsOf}
            setSelectedMonth={setSelectedMonth}
            setSelectedQuarter={setSelectedQuarter}
            setSelectedYear={setSelectedYear}
          />
          <button
            type="button"
            onClick={() => void handleLoad()}
            disabled={loading}
            className={`${whiteButtonClassName} gap-2`}
          >
            <GoIcon />
            {loading ? "Loading" : "Generate"}
          </button>
        </div>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <datalist id="report-month-options">
        {monthOptions.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </datalist>
      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {report.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              {report.report_title}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {report.period_label} - {formatDate(report.period_start)} to{" "}
              {formatDate(report.period_end)} -{" "}
              {formatLabel(report.reporting_mode)}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <select
              value={selectedKind}
              onChange={(event) => handleKindChange(event.target.value as ReportKind)}
              className={`${inputControlClassName} h-10 w-[134px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
              aria-label="Report type"
            >
              {reportKindOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <PeriodControls
              selectedAsOf={selectedAsOf}
              selectedKind={selectedKind}
              selectedMonth={selectedMonth}
              selectedQuarter={selectedQuarter}
              selectedYear={selectedYear}
              setSelectedAsOf={setSelectedAsOf}
              setSelectedMonth={setSelectedMonth}
              setSelectedQuarter={setSelectedQuarter}
              setSelectedYear={setSelectedYear}
            />
            <button
              type="button"
              onClick={() => void handleLoad()}
              disabled={loading}
              className={`${whiteButtonClassName} w-10 px-0`}
              aria-label="Go to selected report"
              title="Go"
            >
              {loading ? <span className="text-xs">...</span> : <GoIcon />}
            </button>
            <button
              type="button"
              onClick={() => void handleSaveSnapshot()}
              disabled={saving}
              className={`${whiteButtonClassName} gap-2`}
            >
              <SaveIcon />
              {saving ? "Saving" : "Save"}
            </button>
            <button
              type="button"
              onClick={handleExport}
              className={`${whiteButtonClassName} gap-2`}
            >
              <PdfIcon />
              Print PDF
            </button>
          </div>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-2 lg:grid-cols-6 lg:divide-x lg:divide-y-0 dark:divide-zinc-800">
          {summaryMetrics.map((metric) => (
            <Metric key={metric.label} {...metric} />
          ))}
        </div>
        {error ? (
          <p className="border-t border-zinc-200 px-5 py-3 text-sm text-amber-700 dark:border-zinc-800 dark:text-amber-300">
            {error}
          </p>
        ) : null}
      </section>

      <ReportTabs activeView={activeView} onChange={handleViewChange} />

      {activeView === "overview" ? (
        <OverviewView
          activeSnapshotKey={`${report.report_kind}:${report.period_key}:${report.generated_at}`}
          compactSections={compactSections}
          archiveAction={archiveAction}
          onSnapshotDelete={handleSnapshotDelete}
          onSnapshotExport={handleSnapshotExport}
          onSnapshotOpen={handleSnapshotOpen}
          onSnapshotPreview={handleSnapshotPreview}
          report={report}
          snapshots={snapshots}
        />
      ) : null}

      {activeView === "attribution" ? (
        <AttributionDetailView detail={report.attribution_detail} report={report} />
      ) : null}

      {activeView === "research" ? <ResearchView report={report} /> : null}

      {activeView === "archive" ? (
        <ArchivePanel
          activeSnapshotKey={`${report.report_kind}:${report.period_key}:${report.generated_at}`}
          maxItems={24}
          archiveAction={archiveAction}
          onDelete={handleSnapshotDelete}
          onExport={handleSnapshotExport}
          onOpen={handleSnapshotOpen}
          onPreview={handleSnapshotPreview}
          snapshots={snapshots}
          title="Saved Reports"
        />
      ) : null}

      <SnapshotModal
        action={archiveAction}
        onClose={() => setSelectedSnapshot(null)}
        onDelete={handleSnapshotDelete}
        onExport={handleSnapshotExport}
        onOpen={handleSnapshotOpen}
        onRename={handleSnapshotRename}
        open={selectedSnapshot !== null}
        setTitle={setSnapshotTitle}
        snapshot={selectedSnapshot}
        title={snapshotTitle}
      />
    </div>
  );
}

function ReportTabs({
  activeView,
  onChange,
}: {
  activeView: ReportCenterView;
  onChange: (view: ReportCenterView) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 rounded-lg border border-zinc-200 bg-white p-1 dark:border-zinc-800 dark:bg-zinc-950">
      {reportViewOptions.map((option) => {
        const isActive = option.value === activeView;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`rounded-md px-3 py-2 text-sm font-medium transition ${
              isActive
                ? "bg-zinc-950 text-white dark:bg-zinc-50 dark:text-zinc-950"
                : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

function OverviewView({
  activeSnapshotKey,
  archiveAction,
  compactSections,
  onSnapshotDelete,
  onSnapshotExport,
  onSnapshotOpen,
  onSnapshotPreview,
  report,
  snapshots,
}: {
  activeSnapshotKey: string;
  archiveAction: string | null;
  compactSections: ReportCompactSection[];
  onSnapshotDelete: (snapshot: ReportSnapshot) => void;
  onSnapshotExport: (snapshot: ReportSnapshot) => void;
  onSnapshotOpen: (snapshot: ReportSnapshot) => void;
  onSnapshotPreview: (snapshot: ReportSnapshot) => void;
  report: MonthlyReport;
  snapshots: ReportSnapshot[];
}) {
  return (
    <div className="space-y-5">
      <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Panel
          title={
            report.report_kind === "monthly"
              ? "Investment Letter"
              : "Report Narrative"
          }
          subtitle={`Generated ${formatDateTime(report.generated_at)}`}
        >
          <p className="max-w-4xl text-sm leading-6 text-zinc-700 dark:text-zinc-300">
            {report.commentary}
          </p>
        </Panel>

        <ArchivePanel
          activeSnapshotKey={activeSnapshotKey}
          archiveAction={archiveAction}
          maxItems={4}
          onDelete={onSnapshotDelete}
          onExport={onSnapshotExport}
          onOpen={onSnapshotOpen}
          onPreview={onSnapshotPreview}
          snapshots={snapshots}
        />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {compactSections.map((section) => (
          <CompactSectionCard key={section.title} section={section} />
        ))}
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <AttributionPanel report={report} />
        <Panel title="Benchmark And Risk">
          <BenchmarkSummary report={report} />
          <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
            {report.risk_warnings.length > 0 ? (
              <div className="space-y-2">
                {report.risk_warnings.slice(0, 5).map((warning) => (
                  <p
                    key={warning}
                    className="text-sm leading-6 text-amber-700 dark:text-amber-300"
                  >
                    {warning}
                  </p>
                ))}
              </div>
            ) : (
              <p className="text-sm text-zinc-500">No active risk warnings.</p>
            )}
          </div>
        </Panel>
      </section>

      <Panel title="Top Positions">
        <Table
          headers={["Ticker", "Asset", "Weight", "Market value", "P/L"]}
          rows={report.top_positions.map((position) => [
            position.ticker,
            formatLabel(position.asset_class),
            pct(position.portfolio_weight_pct),
            money(position.market_value),
            money(position.unrealized_pnl),
          ])}
          empty="No open positions."
        />
      </Panel>
    </div>
  );
}

function ResearchView({ report }: { report: MonthlyReport }) {
  return (
    <section className="grid gap-5 xl:grid-cols-2">
      <Panel title="Research Activity">
        <Table
          headers={["Ticker", "Date", "Classification", "Action", "Score"]}
          rows={report.recent_memos.map((memo) => [
            memo.ticker,
            formatDate(memo.memo_date),
            formatLabel(memo.classification),
            memo.action ? formatLabel(memo.action) : "-",
            memo.composite_score ?? "-",
          ])}
          empty="No ticker memos this period."
        />
      </Panel>

      <Panel title="Research Mix">
        {report.research_summary.length > 0 ? (
          <MetricList items={report.research_summary} />
        ) : (
          <p className="text-sm text-zinc-500">No research mix yet.</p>
        )}
      </Panel>

      <Panel title="Model Registry">
        <Table
          headers={["Model", "Validation"]}
          rows={report.model_registry_summary.map((item) => [
            item.label,
            item.value,
          ])}
          empty="No trained predictive models."
        />
      </Panel>
    </section>
  );
}

function AttributionDetailView({
  detail,
  report,
}: {
  detail: AttributionReport | null;
  report: MonthlyReport;
}) {
  if (!detail) {
    return (
      <Panel title="Performance Attribution">
        <p className="text-sm text-zinc-500">Attribution is not available yet.</p>
      </Panel>
    );
  }

  const summary = detail.summary;
  return (
    <div className="space-y-5">
      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="P/L Bridge" subtitle={report.period_label}>
          <div className="grid gap-3 sm:grid-cols-2">
            <BridgeMetric label="Gross realized" value={summary.gross_realized_pnl} />
            <BridgeMetric label="Unrealized" value={summary.unrealized_pnl} />
            <BridgeMetric label="Fees" value={`-${summary.total_fees}`} />
            <BridgeMetric label="Net P/L" value={summary.net_pnl} emphasis />
          </div>
          <div className="mt-5 space-y-3">
            <BridgeBar label="Realized" value={summary.gross_realized_pnl} />
            <BridgeBar label="Unrealized" value={summary.unrealized_pnl} />
            <BridgeBar label="Costs" value={`-${summary.total_fees}`} />
          </div>
        </Panel>

        <Panel title="Capital Reconciliation" subtitle="External capital against NAV">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SmallMetric label="External flow" value={money(summary.net_external_flow)} />
            <SmallMetric label="Cash" value={money(summary.cash_balance)} />
            <SmallMetric label="Invested" value={money(summary.invested_value)} />
            <SmallMetric label="NAV P/L" value={money(summary.portfolio_pnl_from_nav)} />
            <SmallMetric label="Recon gap" value={money(summary.reconciliation_gap)} />
            <SmallMetric label="Profit factor" value={summary.profit_factor ?? "-"} />
            <SmallMetric label="Deposits" value={money(summary.total_deposits)} />
            <SmallMetric label="Withdrawals" value={money(summary.total_withdrawals)} />
            <SmallMetric label="Fee drag" value={pct(summary.fee_drag_pct)} />
          </div>
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <TickerAttributionTable rows={detail.by_ticker} />
        <div className="space-y-5">
          <BucketPanel title="Asset Class" buckets={detail.by_asset_class} />
          <BucketPanel title="Sector" buckets={detail.by_sector} />
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1fr_0.72fr]">
        <RealizedEvents events={detail.realized_events} />
        <Panel title="Coverage Notes">
          <div className="space-y-3">
            {detail.notes.map((note) => (
              <p
                key={note}
                className="text-sm leading-6 text-zinc-600 dark:text-zinc-300"
              >
                {note}
              </p>
            ))}
          </div>
        </Panel>
      </section>
    </div>
  );
}

function PeriodControls({
  selectedAsOf,
  selectedKind,
  selectedMonth,
  selectedQuarter,
  selectedYear,
  setSelectedAsOf,
  setSelectedMonth,
  setSelectedQuarter,
  setSelectedYear,
}: {
  selectedAsOf: string;
  selectedKind: ReportKind;
  selectedMonth: string;
  selectedQuarter: string;
  selectedYear: string;
  setSelectedAsOf: (value: string) => void;
  setSelectedMonth: (value: string) => void;
  setSelectedQuarter: (value: string) => void;
  setSelectedYear: (value: string) => void;
}) {
  if (selectedKind === "daily") {
    return (
      <input
        type="date"
        value={selectedAsOf}
        onChange={(event) => setSelectedAsOf(event.target.value)}
        className={`${inputControlClassName} h-10 w-[150px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
        aria-label="Report day"
      />
    );
  }

  if (selectedKind === "weekly") {
    return (
      <input
        type="date"
        value={selectedAsOf}
        onChange={(event) => setSelectedAsOf(event.target.value)}
        className={`${inputControlClassName} h-10 w-[150px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
        aria-label="Report week"
      />
    );
  }

  if (selectedKind === "monthly") {
    return (
      <input
        type="month"
        value={selectedMonth}
        onChange={(event) => setSelectedMonth(event.target.value)}
        className={`${inputControlClassName} h-10 w-[150px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
        aria-label="Report month"
        list="report-month-options"
      />
    );
  }

  if (selectedKind === "quarterly") {
    return (
      <>
        <select
          value={selectedQuarter}
          onChange={(event) => setSelectedQuarter(event.target.value)}
          className={`${inputControlClassName} h-10 w-[82px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
          aria-label="Report quarter"
        >
          {quarterOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <YearSelect selectedYear={selectedYear} setSelectedYear={setSelectedYear} />
      </>
    );
  }

  return (
    <YearSelect selectedYear={selectedYear} setSelectedYear={setSelectedYear} />
  );
}

function YearSelect({
  selectedYear,
  setSelectedYear,
}: {
  selectedYear: string;
  setSelectedYear: (value: string) => void;
}) {
  return (
    <select
      value={selectedYear}
      onChange={(event) => setSelectedYear(event.target.value)}
      className={`${inputControlClassName} h-10 w-[108px] dark:border-zinc-200 dark:bg-white dark:text-zinc-800`}
      aria-label="Report year"
    >
      {yearOptions.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function ArchivePanel({
  activeSnapshotKey,
  archiveAction,
  maxItems = 8,
  onDelete,
  onExport,
  onOpen,
  onPreview,
  snapshots,
  title = "Archive",
}: {
  activeSnapshotKey: string;
  archiveAction: string | null;
  maxItems?: number;
  onDelete: (snapshot: ReportSnapshot) => void;
  onExport: (snapshot: ReportSnapshot) => void;
  onOpen: (snapshot: ReportSnapshot) => void;
  onPreview: (snapshot: ReportSnapshot) => void;
  snapshots: ReportSnapshot[];
  title?: string;
}) {
  return (
    <Panel title={title} subtitle={`${snapshots.length} saved`}>
      <div className="space-y-2">
        {snapshots.slice(0, maxItems).map((snapshot) => {
          const key = `${snapshot.report_kind}:${snapshot.payload?.period_key ?? snapshot.period_start}:${snapshot.payload?.generated_at ?? snapshot.created_at}`;
          const isActive = key === activeSnapshotKey;
          const busy =
            archiveAction?.endsWith(`:${snapshot.id}`) || false;
          return (
            <div
              key={snapshot.id}
              className={`rounded-lg border px-3 py-2 transition ${
                isActive
                  ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-50 dark:bg-zinc-50 dark:text-zinc-950"
                  : "border-zinc-200 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <button
                  type="button"
                  onClick={() => onPreview(snapshot)}
                  className="min-w-0 flex-1 text-left"
                >
                  <span className="block truncate text-sm font-medium">
                    {snapshot.title || snapshot.period_label}
                  </span>
                  <span
                    className={`mt-1 block text-xs ${
                      isActive ? "text-zinc-200 dark:text-zinc-700" : "text-zinc-500"
                    }`}
                  >
                    {snapshot.period_label} - {formatLabel(snapshot.report_kind)} -{" "}
                    {formatDate(snapshot.created_at)}
                  </span>
                  <span
                    className={`mt-1 block text-xs tabular-nums ${
                      isActive ? "text-zinc-200 dark:text-zinc-700" : "text-zinc-500"
                    }`}
                  >
                    {snapshot.nav ? money(snapshot.nav) : "-"} /{" "}
                    {snapshot.return_pct ? pct(snapshot.return_pct) : "-"}
                  </span>
                </button>
                <div className="flex shrink-0 items-center gap-1">
                  <ArchiveActionButton
                    disabled={busy}
                    label="Preview"
                    onClick={() => onPreview(snapshot)}
                  />
                  <ArchiveActionButton
                    disabled={busy}
                    label="Open"
                    onClick={() => onOpen(snapshot)}
                  />
                  <ArchiveActionButton
                    disabled={busy}
                    label="PDF"
                    onClick={() => onExport(snapshot)}
                  />
                  <ArchiveActionButton
                    danger
                    disabled={busy}
                    label="Delete"
                    onClick={() => onDelete(snapshot)}
                  />
                </div>
              </div>
            </div>
          );
        })}
        {snapshots.length === 0 ? (
          <p className="text-sm text-zinc-500">No saved reports yet.</p>
        ) : null}
      </div>
    </Panel>
  );
}

function ArchiveActionButton({
  danger,
  disabled,
  label,
  onClick,
}: {
  danger?: boolean;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-md px-2 py-1 text-xs font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${
        danger
          ? "text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950/40"
          : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
      }`}
    >
      {label}
    </button>
  );
}

function SnapshotModal({
  action,
  onClose,
  onDelete,
  onExport,
  onOpen,
  onRename,
  open,
  setTitle,
  snapshot,
  title,
}: {
  action: string | null;
  onClose: () => void;
  onDelete: (snapshot: ReportSnapshot) => void;
  onExport: (snapshot: ReportSnapshot) => void;
  onOpen: (snapshot: ReportSnapshot) => void;
  onRename: () => void;
  open: boolean;
  setTitle: (value: string) => void;
  snapshot: ReportSnapshot | null;
  title: string;
}) {
  const report = snapshot?.payload;
  const busy = snapshot ? action?.endsWith(`:${snapshot.id}`) || false : false;

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Saved Report"
      description={snapshot ? `${snapshot.period_label} / v${snapshot.payload_version}` : undefined}
      size="xl"
      footer={
        snapshot ? (
          <>
            <button
              type="button"
              onClick={onClose}
              className={whiteButtonClassName}
            >
              Close
            </button>
            <button
              type="button"
              onClick={() => onDelete(snapshot)}
              disabled={busy}
              className="inline-flex h-10 items-center justify-center rounded-lg border border-rose-200 bg-white px-4 text-sm font-medium text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-rose-800 dark:bg-zinc-950 dark:text-rose-300 dark:hover:bg-rose-950/40"
            >
              Delete
            </button>
            <button
              type="button"
              onClick={() => onExport(snapshot)}
              disabled={busy || !report}
              className={`${whiteButtonClassName} gap-2`}
            >
              <PdfIcon />
              Print PDF
            </button>
            <button
              type="button"
              onClick={() => onOpen(snapshot)}
              disabled={busy || !report}
              className="inline-flex h-10 items-center justify-center rounded-lg bg-zinc-950 px-4 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-zinc-50 dark:text-zinc-950 dark:hover:bg-zinc-200"
            >
              Open Report
            </button>
          </>
        ) : null
      }
    >
      {snapshot ? (
        <div className="space-y-5">
          <div>
            <label className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Title
            </label>
            <div className="mt-2 flex flex-col gap-2 sm:flex-row">
              <input
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                className={`${inputControlClassName} h-10 flex-1`}
                aria-label="Saved report title"
              />
              <button
                type="button"
                onClick={onRename}
                disabled={busy || title.trim() === ""}
                className={whiteButtonClassName}
              >
                Rename
              </button>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <SmallMetric label="Saved" value={formatDateTime(snapshot.created_at)} />
            <SmallMetric label="NAV" value={snapshot.nav ? money(snapshot.nav) : "-"} />
            <SmallMetric
              label="Return"
              value={snapshot.return_pct ? pct(snapshot.return_pct) : "-"}
            />
          </div>

          {report ? (
            <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                Preview
              </p>
              <h3 className="mt-1 text-lg font-semibold">{report.report_title}</h3>
              <p className="mt-1 text-sm text-zinc-500">
                {report.period_label} - {formatDate(report.period_start)} to{" "}
                {formatDate(report.period_end)}
              </p>
              <p className="mt-4 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                {report.commentary}
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <CompactSectionPreview
                  section={report.ai_overview ?? buildClientAiOverview(report)}
                />
                <CompactSectionPreview section={report.portfolio_positioning} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-zinc-500">Loading saved report payload.</p>
          )}
        </div>
      ) : null}
    </Modal>
  );
}

function CompactSectionPreview({ section }: { section: ReportCompactSection }) {
  return (
    <div>
      <h4 className="text-sm font-semibold">{section.title}</h4>
      <dl className="mt-2 space-y-1.5">
        {section.items.slice(0, 4).map((item) => (
          <div key={item.label} className="flex items-start justify-between gap-3">
            <dt className="text-xs text-zinc-500">{item.label}</dt>
            <dd className="text-right text-xs font-medium text-zinc-700 dark:text-zinc-300">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function CompactSectionCard({ section }: { section: ReportCompactSection }) {
  return (
    <section className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="text-sm font-semibold">{section.title}</h3>
      <dl className="mt-3 space-y-2">
        {section.items.slice(0, 4).map((item) => (
          <div key={item.label} className="flex items-start justify-between gap-3">
            <dt className="text-xs text-zinc-500">{item.label}</dt>
            <dd className="text-right text-sm font-medium tabular-nums">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
      {section.note ? (
        <p className="mt-3 border-t border-zinc-200 pt-3 text-xs leading-5 text-zinc-500 dark:border-zinc-800">
          {section.note}
        </p>
      ) : null}
    </section>
  );
}

function BenchmarkSummary({ report }: { report: MonthlyReport }) {
  const benchmark = report.benchmark_summary;
  if (!benchmark) {
    return <p className="text-sm text-zinc-500">Benchmark data is pending.</p>;
  }

  return (
    <div>
      <div className="grid gap-3 sm:grid-cols-3">
        <SmallMetric
          label={benchmark.benchmark_symbol}
          value={
            benchmark.period_return_pct ? pct(benchmark.period_return_pct) : "-"
          }
        />
        <SmallMetric
          label="Relative"
          value={
            benchmark.relative_return_pct ? pct(benchmark.relative_return_pct) : "-"
          }
        />
        <SmallMetric
          label="Status"
          value={formatLabel(benchmark.status)}
        />
      </div>
      {benchmark.notes.length > 0 ? (
        <p className="mt-3 text-xs leading-5 text-zinc-500">
          {benchmark.notes[0]}
        </p>
      ) : null}
    </div>
  );
}

function AttributionPanel({ report }: { report: MonthlyReport }) {
  const attribution = report.attribution;
  if (!attribution) {
    return (
      <Panel title="Performance Attribution">
        <p className="text-sm text-zinc-500">Attribution is not available yet.</p>
      </Panel>
    );
  }

  return (
    <Panel
      title="Performance Attribution"
      subtitle="Recorded trade and position contribution"
    >
      <div className="grid gap-3 sm:grid-cols-4">
        <SmallMetric label="Net P/L" value={money(attribution.net_pnl)} />
        <SmallMetric label="Return" value={pct(attribution.total_return_pct)} />
        <SmallMetric label="Turnover" value={pct(attribution.turnover_pct)} />
        <SmallMetric
          label="Hit rate"
          value={attribution.hit_rate_pct ? pct(attribution.hit_rate_pct) : "-"}
        />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <AttributionRows
          title="Contributors"
          rows={attribution.top_contributors}
          empty="No positive contributors yet."
        />
        <AttributionRows
          title="Detractors"
          rows={attribution.top_detractors}
          empty="No detractors yet."
        />
      </div>
      {attribution.notes.length > 0 ? (
        <div className="mt-4 space-y-1">
          {attribution.notes.slice(0, 3).map((note) => (
            <p key={note} className="text-xs leading-5 text-zinc-500">
              {note}
            </p>
          ))}
        </div>
      ) : null}
    </Panel>
  );
}

function AttributionRows({
  empty,
  rows,
  title,
}: {
  empty: string;
  rows: MonthlyReportAttributionRow[];
  title: string;
}) {
  return (
    <div>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </h4>
      <div className="mt-2 space-y-2">
        {rows.map((row) => (
          <div
            key={row.ticker}
            className="flex items-center justify-between gap-4 border-b border-zinc-100 py-2 last:border-0 dark:border-zinc-900"
          >
            <div className="min-w-0">
              <p className="text-sm font-medium">{row.ticker}</p>
              <p className="truncate text-xs text-zinc-500">{row.name}</p>
            </div>
            <div className="text-right">
              <p className={`text-sm font-semibold ${toneClass(tone(row.net_pnl))}`}>
                {money(row.net_pnl)}
              </p>
              <p className="text-xs text-zinc-500">
                {pct(row.contribution_pct_nav)} NAV
              </p>
            </div>
          </div>
        ))}
        {rows.length === 0 ? <p className="text-sm text-zinc-500">{empty}</p> : null}
      </div>
    </div>
  );
}

function TickerAttributionTable({ rows }: { rows: AttributionRow[] }) {
  return (
    <Panel title="Ticker Attribution" subtitle="Contribution after recorded fees">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>Ticker</Th>
              <Th>Status</Th>
              <Th>Weight</Th>
              <Th>Realized</Th>
              <Th>Unrealized</Th>
              <Th>Fees</Th>
              <Th>Net P/L</Th>
              <Th>Contribution</Th>
              <Th>Trades</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.instrument.id}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
              >
                <Td>
                  <div>
                    <p className="font-medium">{row.instrument.ticker}</p>
                    <p className="text-xs text-zinc-500">{row.instrument.name}</p>
                  </div>
                </Td>
                <Td>{formatLabel(row.status)}</Td>
                <Td>{pct(row.portfolio_weight_pct)}</Td>
                <Td tone={tone(row.gross_realized_pnl)}>
                  {money(row.gross_realized_pnl)}
                </Td>
                <Td tone={tone(row.unrealized_pnl)}>{money(row.unrealized_pnl)}</Td>
                <Td tone="cost">{money(row.fees)}</Td>
                <Td tone={tone(row.net_pnl)}>{money(row.net_pnl)}</Td>
                <Td>
                  <Contribution value={row.contribution_pct_nav} />
                </Td>
                <Td>{row.trade_count}</Td>
              </tr>
            ))}
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-5 py-10 text-center text-sm text-zinc-500"
                >
                  No attribution rows yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function BucketPanel({
  buckets,
  title,
}: {
  buckets: AttributionBucket[];
  title: string;
}) {
  return (
    <Panel title={title} subtitle="Exposure and net P/L">
      <div className="space-y-3">
        {buckets.map((bucket) => (
          <div
            key={bucket.name}
            className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-medium">{formatLabel(bucket.name)}</p>
                <p className="text-xs text-zinc-500">
                  {bucket.instrument_count} instrument
                  {bucket.instrument_count === 1 ? "" : "s"}
                </p>
              </div>
              <p className={`text-sm font-semibold ${toneClass(tone(bucket.net_pnl))}`}>
                {money(bucket.net_pnl)}
              </p>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <span className="text-zinc-500">Weight {pct(bucket.exposure_pct)}</span>
              <span className="text-zinc-500">
                Realized {money(bucket.gross_realized_pnl)}
              </span>
              <span className="text-zinc-500">Fees {money(bucket.fees)}</span>
            </div>
          </div>
        ))}
        {buckets.length === 0 ? (
          <p className="text-sm text-zinc-500">No bucket attribution yet.</p>
        ) : null}
      </div>
    </Panel>
  );
}

function RealizedEvents({ events }: { events: AttributionRealizedEvent[] }) {
  return (
    <Panel title="Realized Exits" subtitle="Closed trade outcomes">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>Date</Th>
              <Th>Ticker</Th>
              <Th>Qty</Th>
              <Th>Cost</Th>
              <Th>Exit</Th>
              <Th>Return</Th>
              <Th>Net P/L</Th>
            </tr>
          </thead>
          <tbody>
            {events.map((event) => (
              <tr
                key={event.trade_id}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
              >
                <Td>{formatDate(event.trade_date)}</Td>
                <Td emphasis>{event.instrument.ticker}</Td>
                <Td>{Number(event.quantity).toLocaleString()}</Td>
                <Td>{money(event.average_cost)}</Td>
                <Td>{money(event.exit_price)}</Td>
                <Td tone={tone(event.return_pct)}>{pct(event.return_pct)}</Td>
                <Td tone={tone(event.net_realized_pnl)}>
                  {money(event.net_realized_pnl)}
                </Td>
              </tr>
            ))}
            {events.length === 0 ? (
              <tr>
                <td
                  colSpan={7}
                  className="px-5 py-10 text-center text-sm text-zinc-500"
                >
                  No realized exits yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function BridgeMetric({
  emphasis,
  label,
  value,
}: {
  emphasis?: boolean;
  label: string;
  value: string;
}) {
  const currentTone = tone(value);
  return (
    <div
      className={`rounded-lg border p-3 ${
        emphasis
          ? "border-zinc-300 bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900"
          : "border-zinc-100 bg-zinc-50 dark:border-zinc-900 dark:bg-zinc-900/50"
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className={`mt-1 text-lg font-semibold ${toneClass(currentTone)}`}>
        {money(value)}
      </p>
    </div>
  );
}

function BridgeBar({ label, value }: { label: string; value: string }) {
  const numeric = Number(value);
  const width = Math.min(Math.abs(numeric), 100);
  const positive = numeric >= 0;
  return (
    <div>
      <div className="flex items-center justify-between gap-3 text-xs text-zinc-500">
        <span>{label}</span>
        <span>{money(value)}</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-zinc-100 dark:bg-zinc-900">
        <div
          className={`h-2 rounded-full ${positive ? "bg-emerald-500" : "bg-rose-500"}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function Contribution({ value }: { value: string }) {
  const numeric = Number(value);
  const width = Math.min(Math.abs(numeric), 100);
  const positive = numeric >= 0;
  return (
    <div className="min-w-32">
      <span className={toneClass(tone(value))}>{pct(value)}</span>
      <div className="mt-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-900">
        <div
          className={`h-1.5 rounded-full ${positive ? "bg-emerald-500" : "bg-rose-500"}`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

function Th({ children }: { children: ReactNode }) {
  return (
    <th className="whitespace-nowrap px-5 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
      {children}
    </th>
  );
}

function Td({
  children,
  emphasis,
  tone,
}: {
  children: ReactNode;
  emphasis?: boolean;
  tone?: string;
}) {
  return (
    <td
      className={`whitespace-nowrap px-5 py-3 align-middle ${
        emphasis ? "font-medium" : ""
      } ${tone ? toneClass(tone) : "text-zinc-700 dark:text-zinc-300"}`}
    >
      {children}
    </td>
  );
}

function Panel({
  children,
  subtitle,
  title,
}: {
  children: ReactNode;
  subtitle?: string;
  title: string;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle ? <p className="mt-1 text-sm text-zinc-500">{subtitle}</p> : null}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Metric({
  label,
  tone: metricTone,
  value,
}: {
  label: string;
  tone: string;
  value: string;
}) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className={`mt-2 text-xl font-semibold tabular-nums ${toneClass(metricTone)}`}>
        {value}
      </p>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-zinc-500">{label}</p>
      <p className="mt-1 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function MetricList({ items }: { items: { label: string; value: string }[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map((item) => (
        <SmallMetric key={item.label} label={item.label} value={item.value} />
      ))}
    </div>
  );
}

function Table({
  empty,
  headers,
  rows,
}: {
  empty: string;
  headers: string[];
  rows: string[][];
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">{empty}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800">
            {headers.map((header) => (
              <th
                key={header}
                className="pb-3 pr-4 text-xs font-medium uppercase tracking-wide text-zinc-500 last:pr-0"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
            >
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="py-3 pr-4 last:pr-0">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GoIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
    >
      <path d="M5 12h14" />
      <path d="m13 6 6 6-6 6" />
    </svg>
  );
}

function PdfIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
      <path d="M8 13h1.5a1.5 1.5 0 0 1 0 3H8v-5" />
      <path d="M13 11v5" />
      <path d="M13 11h1.2a2.3 2.3 0 0 1 0 5H13" />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className="h-4 w-4"
      fill="none"
      stroke="currentColor"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeWidth="2"
    >
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z" />
      <path d="M17 21v-8H7v8" />
      <path d="M7 3v5h8" />
    </svg>
  );
}

function buildReportLines(report: MonthlyReport) {
  const lines = [
    `${report.portfolio_name} - ${report.period_label} ${report.report_title}`,
    "",
    `Period: ${formatDate(report.period_start)} to ${formatDate(report.period_end)}`,
    `Generated: ${formatDateTime(report.generated_at)}`,
    "",
    "Commentary",
    report.commentary,
    "",
    "Summary",
    `NAV: ${money(report.nav)}`,
    `Cash: ${money(report.cash_balance)}`,
    `Invested: ${money(report.invested_value)}`,
    `Period cash flow: ${money(report.period_cash_flow)}`,
    `Trades: ${report.period_trade_count}`,
    `Research memos: ${report.period_memo_count}`,
    `Risk warnings: ${report.risk_warning_count}`,
    `Cumulative return: ${report.cumulative_return_pct ? pct(report.cumulative_return_pct) : "-"}`,
    "",
  ];

  if (report.benchmark_summary) {
    lines.push(
      "Benchmark",
      `${report.benchmark_summary.benchmark_symbol}: ${
        report.benchmark_summary.period_return_pct
          ? pct(report.benchmark_summary.period_return_pct)
          : "-"
      }`,
      `Relative return: ${
        report.benchmark_summary.relative_return_pct
          ? pct(report.benchmark_summary.relative_return_pct)
          : "-"
      }`,
      "",
    );
  }

  if (report.attribution) {
    lines.push(
      "Attribution",
      `Net P/L: ${money(report.attribution.net_pnl)}`,
      `Return: ${pct(report.attribution.total_return_pct)}`,
      `Fees: ${money(report.attribution.total_fees)}`,
      `Turnover: ${pct(report.attribution.turnover_pct)}`,
      "",
      "Contributors",
      ...exportRows(report.attribution.top_contributors),
      "",
      "Detractors",
      ...exportRows(report.attribution.top_detractors),
      "",
    );
  }

  const aiOverview = report.ai_overview ?? buildClientAiOverview(report);
  lines.push(
    aiOverview.title,
    ...aiOverview.items.map((item) => `${item.label}: ${item.value}`),
    ...(aiOverview.note ? [aiOverview.note] : []),
    "",
  );

  [
    report.portfolio_positioning,
    report.market_commentary,
    report.strategy_changes,
    report.research_pipeline,
  ].forEach((section) => {
    lines.push(section.title);
    section.items.forEach((item) => lines.push(`${item.label}: ${item.value}`));
    if (section.note) lines.push(section.note);
    lines.push("");
  });

  lines.push(
    "Top Positions",
    ...report.top_positions.map(
      (position) =>
        `${position.ticker}: ${money(position.market_value)}, ${pct(position.portfolio_weight_pct)} weight, ${money(position.unrealized_pnl)} P/L`,
    ),
    "",
    "Research Activity",
    ...report.recent_memos.map(
      (memo) =>
        `${memo.ticker}: ${formatLabel(memo.classification)} / ${memo.action ? formatLabel(memo.action) : "No action"} / score ${memo.composite_score ?? "-"}`,
    ),
    "",
    "Risk",
    ...(report.risk_warnings.length
      ? report.risk_warnings
      : ["No active risk warnings."]),
    "",
  );

  return lines;
}

function exportRows(rows: MonthlyReportAttributionRow[]) {
  if (rows.length === 0) return ["None."];
  return rows.map(
    (row) =>
      `${row.ticker}: ${money(row.net_pnl)} (${pct(row.contribution_pct_nav)} NAV)`,
  );
}

function printReport(report: MonthlyReport) {
  const printWindow = window.open("", "_blank", "noopener,noreferrer,width=1024,height=768");
  if (!printWindow) {
    const blob = buildPdfReport(report);
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${reportSlug(report)}.pdf`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
    return;
  }

  printWindow.document.write(buildPrintableReportHtml(report));
  printWindow.document.close();
  printWindow.focus();
  window.setTimeout(() => {
    printWindow.print();
  }, 250);
}

function buildPrintableReportHtml(report: MonthlyReport) {
  const aiOverview = report.ai_overview ?? buildClientAiOverview(report);
  const summaryRows = [
    ["NAV", money(report.nav)],
    ["Cash", money(report.cash_balance)],
    ["Invested", money(report.invested_value)],
    ["Period cash flow", money(report.period_cash_flow)],
    ["Trades", String(report.period_trade_count)],
    ["Research memos", String(report.period_memo_count)],
    ["Risk warnings", String(report.risk_warning_count)],
    [
      "Cumulative return",
      report.cumulative_return_pct ? pct(report.cumulative_return_pct) : "-",
    ],
  ];
  const attributionRows = report.attribution
    ? [
        ["Net P/L", money(report.attribution.net_pnl)],
        ["Period return", pct(report.attribution.total_return_pct)],
        ["Fees", money(report.attribution.total_fees)],
        ["Turnover", pct(report.attribution.turnover_pct)],
        ["Hit rate", report.attribution.hit_rate_pct ? pct(report.attribution.hit_rate_pct) : "-"],
      ]
    : [];

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(report.portfolio_name)} - ${escapeHtml(report.period_label)}</title>
  <style>
    @page { margin: 0.65in; }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: #18181b;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 12px;
      line-height: 1.5;
    }
    header {
      border-bottom: 2px solid #18181b;
      margin-bottom: 24px;
      padding-bottom: 16px;
    }
    .eyebrow {
      color: #71717a;
      font-size: 10px;
      font-weight: 700;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }
    h1 {
      font-size: 28px;
      line-height: 1.15;
      margin: 4px 0 8px;
    }
    h2 {
      border-bottom: 1px solid #d4d4d8;
      font-size: 15px;
      margin: 24px 0 10px;
      padding-bottom: 6px;
    }
    p { margin: 0 0 10px; }
    table {
      border-collapse: collapse;
      margin: 8px 0 16px;
      page-break-inside: avoid;
      width: 100%;
    }
    th, td {
      border-bottom: 1px solid #e4e4e7;
      padding: 7px 8px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: #52525b;
      font-size: 10px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }
    .grid {
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .box {
      border: 1px solid #d4d4d8;
      break-inside: avoid;
      padding: 12px;
    }
    .metric {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      margin: 5px 0;
    }
    .muted { color: #71717a; }
    .note { color: #52525b; font-size: 11px; margin-top: 8px; }
    .numeric { font-variant-numeric: tabular-nums; text-align: right; }
    @media print {
      button { display: none; }
    }
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">${escapeHtml(report.portfolio_name)}</div>
    <h1>${escapeHtml(report.report_title)}</h1>
    <p class="muted">${escapeHtml(report.period_label)} / ${escapeHtml(formatDate(report.period_start))} to ${escapeHtml(formatDate(report.period_end))} / ${escapeHtml(formatLabel(report.reporting_mode))}</p>
    <p class="muted">Generated ${escapeHtml(formatDateTime(report.generated_at))}</p>
  </header>

  <h2>Commentary</h2>
  <p>${escapeHtml(report.commentary)}</p>

  <div class="grid">
    ${metricBox("Summary", summaryRows)}
    ${metricBox(aiOverview.title, aiOverview.items.map((item) => [item.label, item.value]), aiOverview.note)}
  </div>

  ${report.attribution ? `<h2>Attribution</h2>${metricBox("Performance", attributionRows)}${reportTable(
    ["Ticker", "Name", "Net P/L", "Contribution", "Weight"],
    [
      ...report.attribution.top_contributors,
      ...report.attribution.top_detractors,
    ].map((row) => [
      row.ticker,
      row.name,
      money(row.net_pnl),
      pct(row.contribution_pct_nav),
      pct(row.portfolio_weight_pct),
    ]),
  )}` : ""}

  <h2>Portfolio Positioning</h2>
  ${sectionBox(report.portfolio_positioning)}

  <h2>Market And Risk</h2>
  ${sectionBox(report.market_commentary)}
  ${report.benchmark_summary ? metricBox("Benchmark", [
    [report.benchmark_summary.benchmark_symbol, report.benchmark_summary.period_return_pct ? pct(report.benchmark_summary.period_return_pct) : "-"],
    ["Relative", report.benchmark_summary.relative_return_pct ? pct(report.benchmark_summary.relative_return_pct) : "-"],
    ["Status", formatLabel(report.benchmark_summary.status)],
  ], report.benchmark_summary.notes[0]) : ""}
  ${report.risk_warnings.length ? report.risk_warnings.map((warning) => `<p class="note">${escapeHtml(warning)}</p>`).join("") : `<p class="note">No active risk warnings.</p>`}

  <h2>Top Positions</h2>
  ${reportTable(
    ["Ticker", "Asset", "Weight", "Market value", "P/L"],
    report.top_positions.map((position) => [
      position.ticker,
      formatLabel(position.asset_class),
      pct(position.portfolio_weight_pct),
      money(position.market_value),
      money(position.unrealized_pnl),
    ]),
    "No open positions.",
  )}

  <h2>Research</h2>
  ${sectionBox(report.research_pipeline)}
  ${reportTable(
    ["Ticker", "Date", "Classification", "Action", "Score"],
    report.recent_memos.map((memo) => [
      memo.ticker,
      formatDate(memo.memo_date),
      formatLabel(memo.classification),
      memo.action ? formatLabel(memo.action) : "-",
      memo.composite_score ?? "-",
    ]),
    "No ticker memos this period.",
  )}
</body>
</html>`;
}

function metricBox(
  title: string,
  rows: string[][],
  note?: string | null,
) {
  return `<div class="box"><strong>${escapeHtml(title)}</strong>${rows
    .map(
      ([label, value]) =>
        `<div class="metric"><span class="muted">${escapeHtml(label)}</span><span class="numeric">${escapeHtml(value)}</span></div>`,
    )
    .join("")}${note ? `<p class="note">${escapeHtml(note)}</p>` : ""}</div>`;
}

function sectionBox(section: ReportCompactSection) {
  return metricBox(
    section.title,
    section.items.map((item) => [item.label, item.value]),
    section.note,
  );
}

function reportTable(headers: string[], rows: string[][], empty = "No data.") {
  if (rows.length === 0) return `<p class="note">${escapeHtml(empty)}</p>`;
  return `<table><thead><tr>${headers
    .map((header) => `<th>${escapeHtml(header)}</th>`)
    .join("")}</tr></thead><tbody>${rows
    .map(
      (row) =>
        `<tr>${row
          .map((cell, index) => `<td${index > 1 ? ' class="numeric"' : ""}>${escapeHtml(cell)}</td>`)
          .join("")}</tr>`,
    )
    .join("")}</tbody></table>`;
}

function reportSlug(report: MonthlyReport) {
  return `${report.portfolio_name}-${report.period_label}-${report.report_title}`
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function buildPdfReport(report: MonthlyReport) {
  const lines = buildReportLines(report);
  const wrappedLines = lines.flatMap((line) => wrapPdfLine(line));
  const pages = paginate(wrappedLines, 48);
  const fontObjectId = 3 + pages.length * 2;
  const objects: string[] = [];
  const pageIds = pages.map((_, index) => 3 + index * 2);
  objects[0] = "<< /Type /Catalog /Pages 2 0 R >>";
  objects[1] = `<< /Type /Pages /Kids [${pageIds
    .map((id) => `${id} 0 R`)
    .join(" ")}] /Count ${pages.length} >>`;

  pages.forEach((page, index) => {
    const pageObjectId = 3 + index * 2;
    const contentObjectId = pageObjectId + 1;
    const content = [
      "BT",
      "/F1 10 Tf",
      "54 738 Td",
      "14 TL",
      ...page.map((line) => `(${escapePdfText(line)}) Tj T*`),
      "ET",
    ].join("\n");
    objects[pageObjectId - 1] =
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 ${fontObjectId} 0 R >> >> /Contents ${contentObjectId} 0 R >>`;
    objects[contentObjectId - 1] =
      `<< /Length ${content.length} >>\nstream\n${content}\nendstream`;
  });

  objects[fontObjectId - 1] =
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>";

  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets[index + 1] = pdf.length;
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let index = 1; index <= objects.length; index += 1) {
    pdf += `${String(offsets[index]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return new Blob([pdf], { type: "application/pdf" });
}

function wrapPdfLine(line: string) {
  const normalized = line.trim() ? line : " ";
  const maxLength = 92;
  if (normalized.length <= maxLength) return [normalized];
  const words = normalized.split(/\s+/);
  const rows: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxLength && current) {
      rows.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) rows.push(current);
  return rows;
}

function paginate(lines: string[], pageSize: number) {
  const pages: string[][] = [];
  for (let index = 0; index < lines.length; index += pageSize) {
    pages.push(lines.slice(index, index + pageSize));
  }
  return pages.length ? pages : [["No report data."]];
}

function escapePdfText(value: string) {
  return value
    .replace(/[^\x20-\x7E]/g, "-")
    .replace(/\\/g, "\\\\")
    .replace(/\(/g, "\\(")
    .replace(/\)/g, "\\)");
}

function money(value: string | number | null | undefined) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return currency.format(numeric);
}

function pct(value: string | number | null | undefined) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  return `${percentFormat.format(numeric)}%`;
}

function tone(value: string | number | null | undefined) {
  const numeric = Number(value ?? 0);
  if (!Number.isFinite(numeric) || numeric === 0) return "neutral";
  return numeric > 0 ? "positive" : "negative";
}

function toneClass(value: string) {
  if (value === "positive") return "text-emerald-700 dark:text-emerald-400";
  if (value === "negative") return "text-rose-700 dark:text-rose-400";
  if (value === "risk") return "text-amber-700 dark:text-amber-300";
  return "text-zinc-950 dark:text-zinc-50";
}

function buildClientAiOverview(report: MonthlyReport): ReportCompactSection {
  const periodReturn = Number(report.attribution?.total_return_pct);
  const relativeReturn = Number(report.benchmark_summary?.relative_return_pct);
  const hasPeriodReturn = Number.isFinite(periodReturn);
  const hasRelativeReturn = Number.isFinite(relativeReturn);
  const mainRead = !hasPeriodReturn
    ? "Performance attribution is still forming."
    : periodReturn > 0
      ? "Positive period P/L is the main headline."
      : periodReturn < 0
        ? "Drawdown control is the main headline."
        : "Flat performance keeps risk and research quality in focus.";
  const benchmarkRead = !hasRelativeReturn
    ? "Benchmark comparison is pending."
    : relativeReturn > 0
      ? "Ahead of benchmark"
      : relativeReturn < 0
        ? "Behind benchmark"
        : "In line with benchmark";
  return {
    title: "AI Overview",
    items: [
      { label: "Main read", value: mainRead },
      { label: "Benchmark read", value: benchmarkRead },
      {
        label: "Risk read",
        value:
          report.risk_warning_count === 0
            ? "No active risk warnings"
            : "Risk review needed",
      },
      {
        label: "Activity read",
        value:
          report.period_memo_count > report.period_trade_count
            ? "Research-led"
            : report.period_trade_count > report.period_memo_count
              ? "Execution-led"
              : "Balanced activity",
      },
    ],
    note:
      "Generated from verified ledger, position, attribution, benchmark, and research fields.",
  };
}

function formatDate(value: string) {
  return dateFormatter.format(parseDate(value));
}

function formatDateTime(value: string) {
  return dateFormatter.format(new Date(value));
}

function formatLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function monthInputValue(value: string) {
  return value.slice(0, 7);
}

function currentMonthValue() {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
}

function currentDateValue() {
  return dateValue(new Date());
}

function currentQuarter() {
  return Math.floor(new Date().getMonth() / 3) + 1;
}

function quarterFromDate(value: string) {
  return Math.floor(parseDate(value).getMonth() / 3) + 1;
}

function buildMonthOptions() {
  const options: { label: string; value: string }[] = [];
  const date = new Date();
  for (let index = 0; index < 48; index += 1) {
    const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    options.push({
      label: date.toLocaleDateString("en-US", {
        month: "short",
        year: "numeric",
      }),
      value,
    });
    date.setMonth(date.getMonth() - 1);
  }
  return options;
}

function buildYearOptions() {
  const options: { label: string; value: string }[] = [];
  const currentYear = new Date().getFullYear();
  for (let year = currentYear; year >= currentYear - 7; year -= 1) {
    options.push({ label: String(year), value: String(year) });
  }
  return options;
}

function buildDayOptions() {
  const options: { label: string; value: string }[] = [];
  const date = new Date();
  for (let index = 0; index < 45; index += 1) {
    options.push({
      label: dateFormatter.format(date),
      value: dateValue(date),
    });
    date.setDate(date.getDate() - 1);
  }
  return options;
}

function buildWeekOptions() {
  const options: { label: string; value: string }[] = [];
  const date = startOfWeek(new Date());
  for (let index = 0; index < 52; index += 1) {
    options.push({
      label: `Week of ${dateFormatter.format(date)}`,
      value: dateValue(date),
    });
    date.setDate(date.getDate() - 7);
  }
  return options;
}

function startOfWeek(value: Date) {
  const next = new Date(value);
  const day = next.getDay();
  const mondayOffset = day === 0 ? -6 : 1 - day;
  next.setDate(next.getDate() + mondayOffset);
  return next;
}

function dateValue(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function parseDate(value: string) {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  return new Date(value);
}
