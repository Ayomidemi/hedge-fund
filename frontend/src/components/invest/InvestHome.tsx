"use client";

import Link from "next/link";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import type { InvestHome as InvestHomeData } from "@/lib/api";
import { money, signedMoney } from "@/components/invest/format";

export function InvestHome({ home }: { home: InvestHomeData | null }) {
  if (!home) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Pease Invest could not load your paper account yet. Sign in again or
        refresh.
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
          Portfolio value
        </p>
        <p className="mt-2 text-4xl font-semibold tabular-nums">
          {money(home.portfolio_value)}
        </p>
        <div className="mt-5 grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
          <Metric label="Cash" value={money(home.cash)} />
          <Metric label="Invested" value={money(home.invested)} />
          <Metric label="Buying power" value={money(home.account.buying_power)} />
        </div>
        <p className="mt-4 text-xs text-zinc-500">
          Paper account {home.account.account_number} · {home.account.broker_provider}
        </p>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Your investments</h2>
          <Link href="/invest/search" className={buttonPrimaryClassName}>
            Find a stock
          </Link>
        </div>
        {home.holdings.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-500">
            No holdings yet. Search AAPL, review it, then buy a small paper amount.
          </p>
        ) : (
          <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
            {home.holdings.map((holding) => (
              <li key={holding.ticker} className="flex items-center justify-between py-3">
                <Link
                  href={`/invest/instruments/${holding.ticker}`}
                  className="font-semibold hover:underline"
                >
                  {holding.ticker}
                </Link>
                <div className="text-right text-sm">
                  <p className="tabular-nums">{money(holding.market_value)}</p>
                  <p
                    className={
                      Number(holding.unrealized_pnl) >= 0
                        ? "text-emerald-700"
                        : "text-red-700"
                    }
                  >
                    {signedMoney(holding.unrealized_pnl)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-lg font-semibold">What&apos;s happening</h2>
        <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          {home.headlines.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div className="mt-4 flex flex-wrap gap-2">
          <Link href="/invest/discover" className={buttonSecondaryClassName}>
            Discover
          </Link>
          <Link href="/invest/cash" className={buttonSecondaryClassName}>
            Paper cash
          </Link>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">{value}</p>
    </div>
  );
}
