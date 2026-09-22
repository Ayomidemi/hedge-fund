"use client";

import Link from "next/link";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import type {
  InvestAllocationBucket,
  InvestHolding,
  InvestHome as InvestHomeData,
} from "@/lib/api";
import { money, signedPercent } from "@/components/invest/format";

const quickActions = [
  {
    title: "Compare bills and bonds",
    detail: "T-bills, Treasury notes, FGN bonds, and cash-yield products.",
    href: "/invest/markets",
  },
  {
    title: "Fund paper cash",
    detail: "Top up or reset the simulated Invest brokerage account.",
    href: "/invest/cash",
  },
  {
    title: "Check unusual tape",
    detail: "Retail-safe market context without Capital workflow language.",
    href: "/invest/discover",
  },
  {
    title: "Review orders",
    detail: "Paper fills, cancellations, broker IDs, and warnings.",
    href: "/invest/orders",
  },
];

export function InvestHome({ home }: { home: InvestHomeData | null }) {
  if (!home) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Pease Invest could not load your paper account yet. Sign in again or
        refresh.
      </div>
    );
  }

  const baseCurrency = home.account.base_currency;
  const todayTone =
    Number(home.today_change ?? 0) > 0
      ? "text-emerald-700 dark:text-emerald-300"
      : Number(home.today_change ?? 0) < 0
        ? "text-red-700 dark:text-red-300"
        : "text-zinc-600 dark:text-zinc-400";
  const returnTone =
    Number(home.total_return) > 0
      ? "text-emerald-700 dark:text-emerald-300"
      : Number(home.total_return) < 0
        ? "text-red-700 dark:text-red-300"
        : "text-zinc-600 dark:text-zinc-400";

  return (
    <div className="mx-auto max-w-[1320px] space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-100 p-5 dark:border-zinc-900 sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Paper account {home.account.account_number}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              Invest home
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              Fixed income first. Listed instruments stay as secondary paper trades.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/invest/markets" className={buttonPrimaryClassName}>
              Explore fixed income
            </Link>
            <Link href="/invest/markets" className={buttonSecondaryClassName}>
              Search
            </Link>
          </div>
        </div>

        <div className="grid divide-y divide-zinc-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0 xl:grid-cols-6 dark:divide-zinc-900">
          <SummaryMetric
            label="Portfolio value"
            value={money(home.portfolio_value, baseCurrency)}
            large
          />
          <SummaryMetric label="Cash" value={money(home.cash, baseCurrency)} />
          <SummaryMetric
            label="Invested"
            value={money(home.invested, baseCurrency)}
          />
          <SummaryMetric
            label="Today"
            value={
              home.today_change != null
                ? signedMoney(home.today_change, baseCurrency)
                : "—"
            }
            valueClassName={todayTone}
            subValue={signedPercent(home.today_change_pct)}
          />
          <SummaryMetric
            label="Total return"
            value={signedMoney(home.total_return, baseCurrency)}
            valueClassName={returnTone}
            subValue={signedPercent(home.total_return_pct)}
          />
          <SummaryMetric
            label="Buying power"
            value={money(home.account.buying_power, baseCurrency)}
          />
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[0.95fr_1.05fr]">
        <Panel title="Allocation" eyebrow="Book shape">
          <AllocationList
            allocation={home.allocation}
            fallbackCurrency={baseCurrency}
          />
        </Panel>

        <Panel title="Next actions" eyebrow="Invest workflow">
          <div className="grid gap-3 sm:grid-cols-2">
            {quickActions.map((action) => (
              <Link
                key={action.href}
                href={action.href}
                className="rounded-xl border border-zinc-200 p-4 transition hover:border-emerald-700 hover:bg-emerald-50/40 dark:border-zinc-800 dark:hover:border-emerald-700 dark:hover:bg-emerald-950/20"
              >
                <p className="font-medium">{action.title}</p>
                <p className="mt-1 text-sm leading-5 text-zinc-500">
                  {action.detail}
                </p>
              </Link>
            ))}
          </div>
        </Panel>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
        <HoldingsPanel holdings={home.holdings} />
        <Panel title="Market context" eyebrow="Briefing">
          <div className="space-y-3">
            {home.headlines.map((item) => (
              <p
                key={item}
                className="rounded-xl bg-zinc-50 p-3 text-sm leading-6 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
              >
                {item}
              </p>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link href="/invest/discover" className={buttonSecondaryClassName}>
              Discover
            </Link>
            <Link href="/invest/news" className={buttonSecondaryClassName}>
              News
            </Link>
            <Link href="/invest/activity" className={buttonSecondaryClassName}>
              Activity
            </Link>
          </div>
        </Panel>
      </section>
    </div>
  );
}

function SummaryMetric({
  label,
  large = false,
  subValue,
  value,
  valueClassName,
}: {
  label: string;
  large?: boolean;
  subValue?: string;
  value: string;
  valueClassName?: string;
}) {
  return (
    <div className="px-5 py-4 sm:px-6">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p
        className={`mt-2 font-semibold tabular-nums tracking-tight ${
          large ? "text-3xl" : "text-2xl"
        } ${valueClassName ?? ""}`}
      >
        {value}
      </p>
      {subValue ? <p className="mt-1 text-sm text-zinc-500">{subValue}</p> : null}
    </div>
  );
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
    <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
        {eyebrow}
      </p>
      <h3 className="mt-1 text-lg font-semibold">{title}</h3>
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
      <p className="rounded-xl bg-zinc-50 p-4 text-sm text-zinc-500 dark:bg-zinc-900">
        Nothing allocated yet. Cash will appear here once the paper account is
        ready.
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
            <div className="mt-2 h-2 rounded-full bg-zinc-100 dark:bg-zinc-900">
              <div
                className="h-2 rounded-full bg-emerald-700"
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
    <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 px-5 py-4 dark:border-zinc-900">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Positions
          </p>
          <h3 className="mt-1 text-lg font-semibold">Income and market book</h3>
        </div>
        <Link href="/invest/portfolio" className={buttonSecondaryClassName}>
          Portfolio
        </Link>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr>
              <Th>Instrument</Th>
              <Th>Class</Th>
              <Th>Quantity</Th>
              <Th>Value</Th>
              <Th>Return</Th>
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
                  No paper positions yet. Start with Markets to compare fixed-income products.
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

function signedMoney(value: string | number | null | undefined, currency: string) {
  const amount = Number(value ?? 0);
  const formatted = money(Math.abs(amount), currency);
  if (amount > 0) return `+${formatted}`;
  if (amount < 0) return `-${formatted}`;
  return formatted;
}

function assetClassLabel(value: string | null) {
  if (!value) return "Other";
  if (value === "cash_equivalent") return "Cash equivalent";
  return value.replaceAll("_", " ");
}
