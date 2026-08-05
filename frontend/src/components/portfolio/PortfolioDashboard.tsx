import { OperatingCoreForms } from "@/components/portfolio/OperatingCoreForms";
import Link from "next/link";
import type { OperatingCoreDashboard } from "@/lib/api";

type PortfolioDashboardProps = {
  dashboard: OperatingCoreDashboard | null;
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function asNumber(value: string) {
  return Number(value);
}

function money(value: string) {
  return currency.format(asNumber(value));
}

function pct(value: string) {
  return `${Number(value).toFixed(2)}%`;
}

export function PortfolioDashboard({ dashboard }: PortfolioDashboardProps) {
  if (!dashboard) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Backend unavailable. Check the API server and refresh this page.
      </div>
    );
  }

  const metrics = [
    ["NAV", money(dashboard.nav)],
    ["Cash", money(dashboard.cash_balance)],
    ["Invested", money(dashboard.invested_value)],
    ["Positions", String(dashboard.open_position_count)],
    ["Trades", String(dashboard.trade_count)],
  ];
  const breachedChecks = dashboard.risk_checks.filter((check) => !check.passed);

  return (
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {dashboard.portfolio.name}
            </p>
            <h2 className="mt-1 text-xl font-semibold">Fund Operating Core</h2>
          </div>
          <div
            className={`rounded-md px-3 py-2 text-sm ${
              breachedChecks.length === 0
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
                : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
            }`}
          >
            {breachedChecks.length === 0
              ? "Risk within limits"
              : `${breachedChecks.length} risk breach${breachedChecks.length === 1 ? "" : "es"}`}
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {metrics.map(([label, value]) => (
            <div key={label} className="border-l border-zinc-200 pl-4 dark:border-zinc-800">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                {label}
              </p>
              <p className="mt-2 text-2xl font-semibold tracking-normal">{value}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
            <Panel title="Risk Centre" eyebrow="Controls">
              <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
                {dashboard.risk_checks.map((check) => (
                  <div
                    key={check.limit_type}
                    className="flex items-center justify-between gap-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{check.name}</p>
                      <p className="mt-1 text-xs text-zinc-500">{check.message}</p>
                    </div>
                    <StatusPill passed={check.passed} />
                  </div>
                ))}
              </div>
            </Panel>

            <Panel title="Exposure" eyebrow="Portfolio">
              <div className="space-y-5">
                <ExposureList
                  title="Asset Class"
                  buckets={dashboard.asset_class_exposure}
                />
                <ExposureList title="Sector" buckets={dashboard.sector_exposure} />
              </div>
            </Panel>
          </section>

          <section className="grid gap-4 xl:grid-cols-2">
            <DataTable title="Position Book" eyebrow="Holdings">
              <thead>
                <tr>
                  <Th>Ticker</Th>
                  <Th>Class</Th>
                  <Th>Qty</Th>
                  <Th>Value</Th>
                </tr>
              </thead>
              <tbody>
                {dashboard.positions.map((position) => (
                  <tr key={position.id}>
                    <Td emphasis>{position.instrument.ticker}</Td>
                    <Td>{formatLabel(position.instrument.asset_class)}</Td>
                    <Td>{Number(position.quantity).toLocaleString()}</Td>
                    <Td align="right">{money(position.market_value)}</Td>
                  </tr>
                ))}
                {dashboard.positions.length === 0 && <EmptyRow columns={4} />}
              </tbody>
            </DataTable>

            <DataTable title="Trade Journal" eyebrow="Recent">
              <thead>
                <tr>
                  <Th>Ticker</Th>
                  <Th>Side</Th>
                  <Th>Qty</Th>
                  <Th>Price</Th>
                </tr>
              </thead>
              <tbody>
                {dashboard.recent_trades.map((trade) => (
                  <tr key={trade.id}>
                    <Td emphasis>{trade.instrument.ticker}</Td>
                    <Td>{formatLabel(trade.side)}</Td>
                    <Td>{Number(trade.quantity).toLocaleString()}</Td>
                    <Td align="right">
                      {trade.executed_price ? money(trade.executed_price) : "-"}
                    </Td>
                  </tr>
                ))}
                {dashboard.recent_trades.length === 0 && <EmptyRow columns={4} />}
              </tbody>
            </DataTable>
          </section>

          <DataTable
            title="Cash Ledger"
            eyebrow="Last 10"
            action={<Link className={linkClassName} href="/cash-ledger">View History</Link>}
          >
            <thead>
              <tr>
                <Th>Date</Th>
                <Th>Type</Th>
                <Th>Description</Th>
                <Th>Amount</Th>
              </tr>
            </thead>
            <tbody>
              {dashboard.recent_cash_entries.slice(0, 10).map((entry) => (
                <tr key={entry.id}>
                  <Td>{entry.entry_date}</Td>
                  <Td>{formatLabel(entry.entry_type)}</Td>
                  <Td>{entry.description ?? "-"}</Td>
                  <Td align="right">{money(entry.amount)}</Td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </div>

        <aside className="space-y-5">
          <NextBuildPanel />
          <OperatingCoreForms />
        </aside>
      </div>
    </div>
  );
}

function ExposureList({
  title,
  buckets,
}: {
  title: string;
  buckets: { name: string; exposure_pct: string }[];
}) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <div className="mt-2 space-y-2">
        {buckets.length === 0 && <p className="text-sm text-zinc-500">None</p>}
        {buckets.map((bucket) => (
          <div key={bucket.name}>
            <div className="flex items-center justify-between text-xs">
              <span>{bucket.name}</span>
              <span>{pct(bucket.exposure_pct)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className="h-1.5 rounded-full bg-zinc-950 dark:bg-zinc-100"
                style={{ width: `${Math.min(Number(bucket.exposure_pct), 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DataTable({
  action,
  title,
  eyebrow,
  children,
}: {
  action?: React.ReactNode;
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              {eyebrow}
            </p>
            <h3 className="text-sm font-semibold">{title}</h3>
          </div>
          {action}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">{children}</table>
      </div>
    </div>
  );
}

const linkClassName =
  "rounded-md border border-zinc-200 px-2.5 py-1.5 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900";

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-zinc-200 bg-zinc-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
      {children}
    </th>
  );
}

function Td({
  align = "left",
  children,
  emphasis = false,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
  emphasis?: boolean;
}) {
  return (
    <td
      className={`border-b border-zinc-100 px-4 py-3 text-zinc-700 dark:border-zinc-900 dark:text-zinc-300 ${
        align === "right" ? "text-right" : "text-left"
      } ${emphasis ? "font-medium text-zinc-950 dark:text-zinc-50" : ""}`}
    >
      {children}
    </td>
  );
}

function EmptyRow({ columns }: { columns: number }) {
  return (
    <tr>
      <td colSpan={columns} className="px-4 py-6 text-center text-sm text-zinc-500">
        Empty
      </td>
    </tr>
  );
}

function Panel({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-100 pb-3 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {eyebrow}
        </p>
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      <div className="pt-1">{children}</div>
    </div>
  );
}

function StatusPill({ passed }: { passed: boolean }) {
  return (
    <span
      className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${
        passed
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
      }`}
    >
      {passed ? "Pass" : "Breach"}
    </span>
  );
}

function NextBuildPanel() {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Next Build
      </p>
      <h3 className="mt-1 text-sm font-semibold">Ticker Intelligence</h3>
      <div className="mt-4 space-y-3">
        {[
          "Instrument profile",
          "Fundamental scoring",
          "Valuation snapshot",
          "Portfolio suitability",
        ].map((item) => (
          <div key={item} className="flex items-center gap-3 text-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-950 dark:bg-zinc-100" />
            <span className="text-zinc-700 dark:text-zinc-300">{item}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
