import { getCurrentMonthlyReport, type MonthlyReport } from "@/lib/api";

export default async function ReportsPage() {
  let report: MonthlyReport | null = null;
  let unavailable = false;

  try {
    report = await getCurrentMonthlyReport();
  } catch {
    unavailable = true;
  }

  if (!report) {
    return (
      <section className="mx-auto max-w-[1200px] rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Monthly report
        </p>
        <h2 className="mt-2 text-xl font-semibold">
          {unavailable ? "Backend unavailable" : "Report pending"}
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          The monthly report generator is ready once portfolio data is available.
        </p>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <section className="rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Monthly investment report
            </p>
            <h2 className="mt-2 text-2xl font-semibold tracking-normal">
              {report.month}
            </h2>
          </div>
          <span className="rounded-md border border-zinc-200 px-3 py-1.5 text-sm text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
            {report.portfolio_name}
          </span>
        </div>
        <p className="mt-5 max-w-3xl text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {report.commentary}
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {report.metrics.map((metric) => (
            <Metric key={metric.label} label={metric.label} value={metric.value} />
          ))}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title="Top Positions">
          <Table
            headers={["Ticker", "Asset", "Weight", "Market value", "P/L"]}
            rows={report.top_positions.map((position) => [
              position.ticker,
              position.asset_class,
              `${Number(position.portfolio_weight_pct).toFixed(2)}%`,
              position.market_value,
              position.unrealized_pnl,
            ])}
            empty="No open positions"
          />
        </Panel>

        <Panel title="Research Activity">
          <Table
            headers={["Ticker", "Date", "Classification", "Action", "Score"]}
            rows={report.recent_memos.map((memo) => [
              memo.ticker,
              memo.memo_date,
              memo.classification,
              memo.action ?? "-",
              memo.composite_score ?? "-",
            ])}
            empty="No ticker memos this month"
          />
        </Panel>

        <Panel title="Risk Warnings">
          {report.risk_warnings.length > 0 ? (
            <div className="space-y-2">
              {report.risk_warnings.map((warning) => (
                <p key={warning} className="text-sm leading-6 text-amber-700 dark:text-amber-300">
                  {warning}
                </p>
              ))}
            </div>
          ) : (
            <p className="text-sm text-zinc-500">No active risk warnings</p>
          )}
        </Panel>

        <Panel title="Model Registry">
          <Table
            headers={["Model", "Validation"]}
            rows={report.model_registry_summary.map((item) => [
              item.label,
              item.value,
            ])}
            empty="No trained predictive models"
          />
        </Panel>
      </div>
    </div>
  );
}

function Panel({
  children,
  title,
}: {
  children: React.ReactNode;
  title: string;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 px-3.5 py-3 dark:border-zinc-800">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-1.5 text-lg font-semibold tabular-nums">{value}</p>
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
      <table className="w-full min-w-[560px] text-left text-sm">
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
