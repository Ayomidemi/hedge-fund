import Link from "next/link";
import type { InvestHome } from "@/lib/api";
import { money, signedMoney, signedPercent } from "@/components/invest/format";

export function InvestAccountSummary({ home }: { home: InvestHome }) {
  const currency = home.account.base_currency;
  const tone = Number(home.total_return) < 0 ? "text-red-700 dark:text-red-300" : Number(home.total_return) > 0 ? "text-emerald-800 dark:text-emerald-300" : "";
  return <section aria-label="Invest account balances" className="border-y border-[var(--pease-rule)] bg-[var(--pease-paper)]">
    <dl className="grid grid-cols-2 gap-6 px-5 py-7 sm:px-7 lg:grid-cols-[1.6fr_1fr_1fr] lg:gap-10 lg:py-9">
      <div className="col-span-2 lg:col-span-1"><dt className="text-sm text-stone-500 dark:text-stone-400">Account value <span className="ml-1 text-xs">/ {currency}</span></dt><dd className="mt-2 text-[clamp(2rem,5vw,3.5rem)] leading-none tracking-[-0.025em] tabular-nums">{money(home.portfolio_value, currency)}</dd><dd className="mt-3 text-xs text-stone-500 dark:text-stone-400">Total cash + holdings value</dd></div>
      <div className="lg:border-l lg:border-[var(--pease-rule)] lg:pl-8"><dt className="text-sm text-stone-500 dark:text-stone-400"><Link href="/invest/cash" className="underline-offset-4 hover:underline">Total cash</Link></dt><dd className="mt-2 text-[clamp(1rem,3vw,1.75rem)] tabular-nums">{money(home.cash, currency)}</dd><dd className="mt-3 text-xs text-stone-500 dark:text-stone-400">Buying power <span className="block font-medium tabular-nums sm:inline">{money(home.account.buying_power, currency)}</span></dd></div>
      <div className="lg:border-l lg:border-[var(--pease-rule)] lg:pl-8"><dt className="text-sm text-stone-500 dark:text-stone-400"><Link href="/invest/portfolio" className="underline-offset-4 hover:underline">Holdings value</Link></dt><dd className="mt-2 text-[clamp(1rem,3vw,1.75rem)] tabular-nums">{money(home.invested, currency)}</dd><dd className="mt-3 text-xs text-stone-500 dark:text-stone-400">{home.holdings.length} holding{home.holdings.length === 1 ? "" : "s"}</dd></div>
    </dl>
    <dl className="grid gap-4 border-t border-[var(--pease-rule)] px-5 py-4 text-sm sm:grid-cols-2 sm:px-7">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1"><dt className="text-stone-500 dark:text-stone-400">Total return</dt><dd className={`font-medium tabular-nums ${tone}`}>{signedMoney(home.total_return, currency)} <span className="ml-1 text-xs">{signedPercent(home.total_return_pct)}</span></dd></div>
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 sm:justify-end"><dt className="text-stone-500 dark:text-stone-400">Today</dt><dd className="tabular-nums">{signedMoney(home.today_change, currency)} <span className="ml-1 text-xs text-stone-500 dark:text-stone-400">{signedPercent(home.today_change_pct)}</span></dd></div>
    </dl>
  </section>;
}
