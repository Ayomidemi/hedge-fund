"use client";

import Link from "next/link";
import { useState } from "react";
import { ManualTradeModal } from "@/components/portfolio/ManualTradeModal";
import {
  CashLedgerTypeBadge,
  formatPlatformLabel,
  formatSignedAmount,
} from "@/components/ledger/cash-ledger-ui";
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

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
  }).format(new Date(value));
}

export function PortfolioDashboard({ dashboard }: PortfolioDashboardProps) {
  const [tradeModalOpen, setTradeModalOpen] = useState(false);

  if (!dashboard) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Your workspace could not be loaded yet. Sign in again or refresh this page.
      </div>
    );
  }

  const metrics = [
    { label: "NAV", value: money(dashboard.nav) },
    { label: "Cash", value: money(dashboard.cash_balance) },
    { label: "Invested", value: money(dashboard.invested_value) },
    { label: "Positions", value: String(dashboard.open_position_count) },
    { label: "Trades", value: String(dashboard.trade_count) },
  ];
  const breachedChecks = dashboard.risk_checks.filter((check) => !check.passed);
  const recentCash = dashboard.recent_cash_entries.slice(0, 10);

  return (
    <>
      <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
        <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 sm:p-6">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {dashboard.portfolio.name}
              </p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight">Fund overview</h2>
            </div>
            <div
              className={`rounded-full px-3.5 py-1.5 text-sm font-medium ${
                breachedChecks.length === 0
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
                  : "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300"
              }`}
            >
              {breachedChecks.length === 0
                ? "Risk within limits"
                : `${breachedChecks.length} risk breach${breachedChecks.length === 1 ? "" : "es"}`}
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {metrics.map((metric) => (
              <div
                key={metric.label}
                className="rounded-xl border border-zinc-100 bg-zinc-50/70 px-4 py-3.5 dark:border-zinc-900 dark:bg-zinc-900/40"
              >
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  {metric.label}
                </p>
                <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">
                  {metric.value}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
          <Panel title="Risk centre" eyebrow="Controls">
            <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {dashboard.risk_checks.map((check) => (
                <div
                  key={check.limit_type}
                  className="flex items-center justify-between gap-4 py-3.5"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{check.name}</p>
                    <p className="mt-1 text-xs leading-relaxed text-zinc-500">{check.message}</p>
                  </div>
                  <StatusPill passed={check.passed} />
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Exposure" eyebrow="Portfolio">
            <div className="space-y-5">
              <ExposureList title="Asset class" buckets={dashboard.asset_class_exposure} />
              <ExposureList title="Sector" buckets={dashboard.sector_exposure} />
            </div>
          </Panel>
        </section>

        <section className="grid gap-5 xl:grid-cols-2">
          <DataTable title="Position book" eyebrow="Holdings">
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
              {dashboard.positions.length === 0 && <EmptyRow columns={4} message="No open positions" />}
            </tbody>
          </DataTable>

          <DataTable
            title="Trade journal"
            eyebrow="Recent"
            action={
              <div className="flex items-center gap-2">
                <Link href="/trade-journal" className={ghostButtonClassName}>
                  View all
                </Link>
                <button
                  type="button"
                  onClick={() => setTradeModalOpen(true)}
                  className={ghostButtonClassName}
                >
                  Record trade
                </button>
              </div>
            }
          >
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
                    {trade.executed_price ? money(trade.executed_price) : "—"}
                  </Td>
                </tr>
              ))}
              {dashboard.recent_trades.length === 0 && (
                <EmptyRow columns={4} message="No trades recorded yet" />
              )}
            </tbody>
          </DataTable>
        </section>

        <DataTable
          title="Cash ledger"
          eyebrow="Recent movements"
          action={
            <Link href="/cash-ledger" className={ghostButtonClassName}>
              View all
            </Link>
          }
        >
          <thead>
            <tr>
              <Th>Date</Th>
              <Th>Type</Th>
              <Th>Platform</Th>
              <Th>Description</Th>
              <Th>Amount</Th>
            </tr>
          </thead>
          <tbody>
            {recentCash.map((entry) => (
                <tr key={entry.id}>
                  <Td>{formatDate(entry.entry_date)}</Td>
                  <Td>
                    <CashLedgerTypeBadge type={entry.entry_type} />
                  </Td>
                  <Td>{formatPlatformLabel(entry.platform)}</Td>
                  <Td muted>{entry.description ?? "—"}</Td>
                  <Td align="right">
                    <span className="font-medium tabular-nums">
                      {formatSignedAmount(entry.amount)}
                    </span>
                  </Td>
                </tr>
              ))}
            {recentCash.length === 0 && (
              <EmptyRow
                columns={5}
                message="No cash movements yet — head to the cash ledger to add one"
              />
            )}
          </tbody>
        </DataTable>
      </div>

      <ManualTradeModal open={tradeModalOpen} onClose={() => setTradeModalOpen(false)} />
    </>
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
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">{title}</p>
      <div className="mt-3 space-y-3">
        {buckets.length === 0 && <p className="text-sm text-zinc-500">Nothing allocated yet</p>}
        {buckets.map((bucket) => (
          <div key={bucket.name}>
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-zinc-700 dark:text-zinc-300">{bucket.name}</span>
              <span className="tabular-nums text-zinc-500">{pct(bucket.exposure_pct)}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
              <div
                className="h-full rounded-full bg-zinc-900 dark:bg-zinc-100"
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
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-100 px-5 py-4 dark:border-zinc-900">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            {eyebrow}
          </p>
          <h3 className="mt-1 text-sm font-semibold">{title}</h3>
        </div>
        {action}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-left text-sm">{children}</table>
      </div>
    </div>
  );
}

const ghostButtonClassName =
  "rounded-lg border border-zinc-200 px-3 py-1.5 text-xs font-medium text-zinc-700 transition hover:border-zinc-300 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:border-zinc-700 dark:hover:bg-zinc-900";

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-zinc-100 bg-zinc-50/80 px-5 py-3 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-900 dark:bg-zinc-900/50">
      {children}
    </th>
  );
}

function Td({
  align = "left",
  children,
  emphasis = false,
  muted = false,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
  emphasis?: boolean;
  muted?: boolean;
}) {
  return (
    <td
      className={`border-b border-zinc-100 px-5 py-3.5 dark:border-zinc-900 ${
        align === "right" ? "text-right" : "text-left"
      } ${
        emphasis
          ? "font-medium text-zinc-950 dark:text-zinc-50"
          : muted
            ? "text-zinc-500"
            : "text-zinc-700 dark:text-zinc-300"
      }`}
    >
      {children}
    </td>
  );
}

function EmptyRow({ columns, message }: { columns: number; message: string }) {
  return (
    <tr>
      <td colSpan={columns} className="px-5 py-8 text-center text-sm text-zinc-500">
        {message}
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
    <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-100 pb-4 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
          {eyebrow}
        </p>
        <h3 className="mt-1 text-sm font-semibold">{title}</h3>
      </div>
      <div className="pt-1">{children}</div>
    </div>
  );
}

function StatusPill({ passed }: { passed: boolean }) {
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-medium ${
        passed
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
          : "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300"
      }`}
    >
      {passed ? "Pass" : "Breach"}
    </span>
  );
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
