"use client";

import Link from "next/link";
import { useState } from "react";
import { CashEntryModal } from "@/components/ledger/CashEntryModal";
import {
  CashLedgerTypeBadge,
  formatPlatformLabel,
  formatSignedAmount,
} from "@/components/ledger/cash-ledger-ui";
import { buttonPrimaryClassName } from "@/components/ui/form-styles";
import type { CashLedgerEntry } from "@/lib/api";

type CashLedgerHistoryProps = {
  entries: CashLedgerEntry[];
  isUnavailable?: boolean;
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

export function CashLedgerHistory({
  entries,
  isUnavailable = false,
}: CashLedgerHistoryProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const totalCash = entries.reduce((total, entry) => total + Number(entry.amount), 0);
  const netIn = entries
    .filter((entry) => Number(entry.amount) > 0)
    .reduce((sum, entry) => sum + Number(entry.amount), 0);
  const netOut = entries
    .filter((entry) => Number(entry.amount) < 0)
    .reduce((sum, entry) => sum + Number(entry.amount), 0);

  return (
    <>
      <div className="mx-auto flex max-w-[1200px] flex-col gap-6">
        {isUnavailable && (
          <div className="rounded-lg border border-red-200 bg-white p-4 text-sm text-red-700 dark:border-red-900 dark:bg-zinc-950 dark:text-red-400">
            Cash ledger history unavailable. Check the backend server and refresh.
          </div>
        )}

        <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-6 py-5 dark:border-zinc-800">
            <div>
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Cash balance
              </p>
              <h2 className="mt-1 text-3xl font-semibold tabular-nums tracking-tight">
                {currency.format(totalCash)}
              </h2>
            </div>
            <button
              type="button"
              onClick={() => setModalOpen(true)}
              className={buttonPrimaryClassName}
            >
              New entry
            </button>
          </div>

          <div className="grid divide-y divide-zinc-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
            <Stat label="Total inflows" value={currency.format(netIn)} />
            <Stat label="Total outflows" value={currency.format(Math.abs(netOut))} />
            <Stat label="Entries" value={String(entries.length)} />
          </div>
        </section>

        <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
            <div>
              <h3 className="text-sm font-semibold">Movement history</h3>
              <p className="mt-0.5 text-sm text-zinc-500">
                {entries.length} recorded movement{entries.length === 1 ? "" : "s"}
              </p>
            </div>
            <Link
              href="/"
              className="text-sm text-zinc-500 transition hover:text-zinc-900 dark:hover:text-zinc-100"
            >
              Dashboard
            </Link>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-zinc-800">
                  <Th>Date</Th>
                  <Th>Type</Th>
                  <Th>Platform</Th>
                  <Th>Description</Th>
                  <Th align="right">Amount</Th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                  >
                    <Td>{formatDate(entry.entry_date)}</Td>
                    <Td>
                      <CashLedgerTypeBadge type={entry.entry_type} />
                    </Td>
                    <Td>{formatPlatformLabel(entry.platform)}</Td>
                    <Td muted>{entry.description?.trim() || "—"}</Td>
                    <Td align="right">
                      <span className="font-medium tabular-nums text-zinc-900 dark:text-zinc-100">
                        {formatSignedAmount(entry.amount)}
                      </span>
                    </Td>
                  </tr>
                ))}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-6 py-16 text-center">
                      <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                        No movements yet
                      </p>
                      <p className="mt-1 text-sm text-zinc-500">
                        Record your first entry to start the ledger.
                      </p>
                      <button
                        type="button"
                        onClick={() => setModalOpen(true)}
                        className={`${buttonPrimaryClassName} mt-4`}
                      >
                        New entry
                      </button>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      <CashEntryModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-6 py-4">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-zinc-900 dark:text-zinc-100">
        {value}
      </p>
    </div>
  );
}

function Th({
  align = "left",
  children,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  return (
    <th
      className={`px-6 py-3 text-xs font-medium uppercase tracking-wider text-zinc-500 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </th>
  );
}

function Td({
  align = "left",
  children,
  muted = false,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
  muted?: boolean;
}) {
  return (
    <td
      className={`px-6 py-3.5 ${
        align === "right" ? "text-right" : "text-left"
      } ${muted ? "text-zinc-500" : "text-zinc-800 dark:text-zinc-200"}`}
    >
      {children}
    </td>
  );
}
