"use client";

import type { ReactNode } from "react";
import type {
  AttributionBucket,
  AttributionRealizedEvent,
  AttributionReport,
  AttributionRow,
} from "@/lib/api";

type AttributionDashboardProps = {
  report: AttributionReport | null;
  isUnavailable: boolean;
};

const currency = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 2,
  style: "currency",
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function AttributionDashboard({
  report,
  isUnavailable,
}: AttributionDashboardProps) {
  if (!report) {
    return (
      <section className="mx-auto max-w-[1200px] rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Performance attribution
        </p>
        <h2 className="mt-2 text-xl font-semibold">
          {isUnavailable ? "Attribution could not be loaded yet" : "Attribution pending"}
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          {isUnavailable
            ? "Sign in again or refresh this page."
            : "Trade and position data will appear here once available."}
        </p>
      </section>
    );
  }

  const summary = report.summary;
  const period = summary.period_start
    ? `${formatDate(summary.period_start)} to ${formatDate(summary.period_end)}`
    : `Through ${formatDate(summary.period_end)}`;
  const metrics = [
    { label: "NAV", value: money(summary.nav), tone: "neutral" },
    { label: "Net P/L", value: money(summary.net_pnl), tone: tone(summary.net_pnl) },
    { label: "Return", value: pct(summary.total_return_pct), tone: tone(summary.total_return_pct) },
    { label: "Fees", value: money(summary.total_fees), tone: "cost" },
    { label: "Hit rate", value: optionalPct(summary.hit_rate_pct), tone: "neutral" },
    { label: "Turnover", value: pct(summary.turnover_pct), tone: "neutral" },
  ];

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {summary.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              Performance Attribution
            </h2>
            <p className="mt-1 text-sm text-zinc-500">{period}</p>
          </div>
          <div className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
            {summary.trade_count} trade{summary.trade_count === 1 ? "" : "s"}
          </div>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-2 lg:grid-cols-6 lg:divide-x lg:divide-y-0 dark:divide-zinc-800">
          {metrics.map((metric) => (
            <Metric key={metric.label} {...metric} />
          ))}
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
        <Panel title="P/L Bridge" subtitle="Realized, unrealized, and transaction-cost effect">
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

        <Panel title="Capital Reconciliation" subtitle="External capital against current NAV">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <SmallMetric label="External flow" value={money(summary.net_external_flow)} />
            <SmallMetric label="Cash" value={money(summary.cash_balance)} />
            <SmallMetric label="Invested" value={money(summary.invested_value)} />
            <SmallMetric label="NAV P/L" value={money(summary.portfolio_pnl_from_nav)} />
            <SmallMetric label="Recon gap" value={money(summary.reconciliation_gap)} />
            <SmallMetric label="Profit factor" value={summary.profit_factor ?? "-"} />
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <SmallMetric label="Deposits" value={money(summary.total_deposits)} />
            <SmallMetric label="Withdrawals" value={money(summary.total_withdrawals)} />
            <SmallMetric label="Fee drag" value={pct(summary.fee_drag_pct)} />
          </div>
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <TickerAttributionTable rows={report.by_ticker} />
        <div className="space-y-5">
          <BucketPanel title="Asset Class" buckets={report.by_asset_class} />
          <BucketPanel title="Sector" buckets={report.by_sector} />
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1fr_0.72fr]">
        <RealizedEvents events={report.realized_events} />
        <Panel title="Coverage Notes">
          <div className="space-y-3">
            {report.notes.map((note) => (
              <p key={note} className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
                {note}
              </p>
            ))}
          </div>
        </Panel>
      </section>
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
                <Td tone={tone(row.gross_realized_pnl)}>{money(row.gross_realized_pnl)}</Td>
                <Td tone={tone(row.unrealized_pnl)}>{money(row.unrealized_pnl)}</Td>
                <Td tone="cost">{money(row.fees)}</Td>
                <Td tone={tone(row.net_pnl)}>{money(row.net_pnl)}</Td>
                <Td>
                  <Contribution value={row.contribution_pct_nav} />
                </Td>
                <Td>{row.trade_count}</Td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={9} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No attribution rows yet.
                </td>
              </tr>
            )}
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
              <span className="text-zinc-500">Realized {money(bucket.gross_realized_pnl)}</span>
              <span className="text-zinc-500">Fees {money(bucket.fees)}</span>
            </div>
          </div>
        ))}
        {buckets.length === 0 && (
          <p className="text-sm text-zinc-500">No bucket attribution yet.</p>
        )}
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
                <Td tone={tone(event.net_realized_pnl)}>{money(event.net_realized_pnl)}</Td>
              </tr>
            ))}
            {events.length === 0 && (
              <tr>
                <td colSpan={7} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No realized exits yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Panel>
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
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function Metric({
  label,
  tone,
  value,
}: {
  label: string;
  tone: string;
  value: string;
}) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-2 text-xl font-semibold tabular-nums tracking-tight ${toneClass(tone)}`}>
        {value}
      </p>
    </div>
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
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-1 text-lg font-semibold ${toneClass(currentTone)}`}>
        {money(value)}
      </p>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 truncate text-sm font-semibold tabular-nums">{value}</p>
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
      <div className="flex items-center justify-between gap-2">
        <span className={toneClass(tone(value))}>{pct(value)}</span>
      </div>
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

function money(value: string) {
  return currency.format(Number(value));
}

function pct(value: string) {
  return `${Number(value).toFixed(2)}%`;
}

function optionalPct(value: string | null) {
  return value === null ? "-" : pct(value);
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function tone(value: string) {
  const numeric = Number(value);
  if (numeric > 0) return "positive";
  if (numeric < 0) return "negative";
  return "neutral";
}

function toneClass(value: string) {
  if (value === "positive") return "text-emerald-700 dark:text-emerald-300";
  if (value === "negative") return "text-rose-700 dark:text-rose-300";
  if (value === "cost") return "text-amber-700 dark:text-amber-300";
  return "text-zinc-950 dark:text-zinc-50";
}
