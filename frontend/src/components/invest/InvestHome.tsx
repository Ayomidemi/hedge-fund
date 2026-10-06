"use client";

import Link from "next/link";
import {
  buttonPrimaryClassName,
} from "@/components/ui/form-styles";
import type {
  InvestAllocationBucket,
  InvestHolding,
  InvestHome as InvestHomeData,
} from "@/lib/api";
import { InvestAccountSummary } from "@/components/invest/InvestAccountSummary";
import { money, signedMoney, signedPercent } from "@/components/invest/format";

export function InvestHome({ home }: { home: InvestHomeData | null }) {
  if (!home) {
    return (
      <div className="rounded-sm border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Pease Invest could not load your paper account yet. Sign in again or
        refresh.
      </div>
    );
  }

  const baseCurrency = home.account.base_currency;
  return <div className="space-y-9">
    <div className="flex flex-wrap items-end justify-between gap-5">
      <div><p className="mb-2 text-xs text-stone-500 dark:text-stone-400">Paper account · {home.account.account_number}</p><h2 className="text-3xl sm:text-4xl">Your investments.</h2></div>
      <Link href="/invest/markets" className="inline-flex items-center gap-8 border border-[#4b583d] bg-[#4b583d] px-5 py-3 text-sm text-white transition hover:bg-[#3a462e]">Explore investments <span aria-hidden="true">↗</span></Link>
    </div>
    <InvestAccountSummary home={home} />
    <div className="grid items-start gap-9 xl:grid-cols-[minmax(0,1fr)_300px]">
      <HoldingsPanel holdings={home.holdings} />
      <Panel title="Where your money is" eyebrow="Allocation"><AllocationList allocation={home.allocation} fallbackCurrency={baseCurrency} /></Panel>
    </div>
    <div className="grid gap-9 border-t border-[var(--pease-rule)] pt-7 lg:grid-cols-2">
      <Panel title="From the desk" eyebrow="Market notes">
        <div className="divide-y divide-[var(--pease-rule)]">{home.headlines.map(item => <p key={item} className="py-3 text-sm leading-6 text-stone-600 first:pt-0 dark:text-stone-400">{item}</p>)}{home.headlines.length === 0 ? <p className="text-sm text-stone-500">Market notes will appear when available.</p> : null}</div>
        <Link href="/invest/news" className="mt-5 inline-block text-sm underline decoration-stone-400 underline-offset-4">Read the news ↗</Link>
      </Panel>
      <Panel title="Your next move" eyebrow="Quick links">
        <div className="divide-y divide-[var(--pease-rule)]">{home.quick_actions.map(action => <Link key={action.href} href={action.href} className="group flex items-start justify-between gap-4 py-4 first:pt-0"><div><p className="font-medium group-hover:underline">{action.title}</p><p className="mt-1 text-sm text-stone-500 dark:text-stone-400">{action.detail}</p></div><span className="pt-1 text-stone-500" aria-hidden="true">↗</span></Link>)}</div>
      </Panel>
    </div>
  </div>;
}

function Panel({
  children,
  eyebrow,
  title,
}: {
  children: React.ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <section className="min-w-0">
      <p className="text-xs text-stone-500 dark:text-stone-400">
        {eyebrow}
      </p>
      <h3 className="pease-editorial mt-1 text-xl">{title}</h3>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function AllocationList({
  allocation,
  fallbackCurrency,
}: {
  allocation: InvestAllocationBucket[];
  fallbackCurrency: string;
}) {
  if (allocation.length === 0) {
    return (
      <p className="border-t border-[var(--pease-rule)] py-5 text-sm text-stone-500">
        No allocation data is available yet.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      {allocation.map((bucket) => {
        const pct = Math.max(0, Math.min(100, Number(bucket.allocation_pct)));
        return (
          <div key={bucket.name}>
            <div className="flex items-baseline justify-between gap-3">
              <p className="text-sm font-medium">{bucket.name}</p>
              <p className="text-sm tabular-nums text-zinc-500">
                {money(bucket.value, fallbackCurrency)} - {pct.toFixed(2)}%
              </p>
            </div>
            <div className="mt-2 h-2 bg-stone-200 dark:bg-zinc-900">
              <div
                className="h-2 bg-[#647252]"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HoldingsPanel({
  holdings,
}: {
  holdings: InvestHolding[];
}) {
  return (
    <section className="min-w-0 overflow-hidden">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs text-stone-500 dark:text-stone-400">
            Positions
          </p>
          <h3 className="pease-editorial mt-1 text-xl">Your holdings</h3>
        </div>
        <Link href="/invest/portfolio" className="text-sm underline underline-offset-4">
          View portfolio
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-left text-sm">
          <thead>
            <tr>
              <Th>Instrument</Th>
              <Th>Class</Th>
              <Th>Quantity</Th>
              <Th>Value</Th>
              <Th>Unrealized P/L</Th>
              <Th>Weight</Th>
            </tr>
          </thead>
          <tbody>
            {holdings.map((holding) => (
              <tr key={holding.ticker}>
                <Td>
                  <Link
                    href={holding.href ?? `/invest/instruments/${holding.ticker}`}
                    className="font-semibold text-zinc-950 hover:underline dark:text-zinc-50"
                  >
                    {holding.ticker}
                  </Link>
                  <p className="mt-1 text-xs text-zinc-500">{holding.name}</p>
                </Td>
                <Td>{assetClassLabel(holding.asset_class)}</Td>
                <Td>{Number(holding.quantity).toLocaleString()}</Td>
                <Td align="right">
                  {money(holding.market_value, holding.currency)}
                </Td>
                <Td align="right">
                  <span
                    className={
                      Number(holding.unrealized_pnl) >= 0
                        ? "text-emerald-700 dark:text-emerald-300"
                        : "text-red-700 dark:text-red-300"
                    }
                  >
                    {signedMoney(holding.unrealized_pnl, holding.currency)}
                  </span>
                  <p className="mt-1 text-xs text-zinc-500">
                    {signedPercent(holding.unrealized_pnl_pct)}
                  </p>
                </Td>
                <Td align="right">
                  {holding.allocation_pct ? `${Number(holding.allocation_pct).toFixed(2)}%` : "-"}
                </Td>
              </tr>
            ))}
            {holdings.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No holdings yet. Explore markets to find your first investment.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      {holdings.length === 0 ? (
        <div className="border-t border-zinc-100 px-5 py-4 dark:border-zinc-900">
          <Link href="/invest/markets" className={buttonPrimaryClassName}>
            Open markets
          </Link>
        </div>
      ) : null}
    </section>
  );
}

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
}: {
  align?: "left" | "right";
  children: React.ReactNode;
}) {
  return (
    <td
      className={`border-b border-zinc-100 px-5 py-3.5 align-top text-zinc-700 dark:border-zinc-900 dark:text-zinc-300 ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      {children}
    </td>
  );
}

function assetClassLabel(value: string | null) {
  if (!value) return "Other";
  if (value === "cash_equivalent") return "Cash equivalent";
  return value.replaceAll("_", " ");
}
