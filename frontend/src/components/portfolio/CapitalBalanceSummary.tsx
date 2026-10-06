import type { OperatingCoreDashboard, PaperFundRun } from "@/lib/api";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function capitalMoney(value: string | number | null | undefined) {
  return value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
    ? usd.format(Number(value)) : "—";
}

/** Cash reservations are part of total cash, never additional account value. */
export function CapitalBalanceSummary({ capital, run, compact = false }: {
  capital: OperatingCoreDashboard;
  run: PaperFundRun | null;
  compact?: boolean;
}) {
  const available = run ? run.available_cash : capital.cash_balance;
  const reserved = run ? run.reserved_cash : "0";
  return <div aria-label="Capital account balances">
    <dl className={`grid grid-cols-2 gap-6 ${compact ? "sm:grid-cols-[1.2fr_1fr_1fr]" : "lg:grid-cols-[1.4fr_1fr_1fr]"}`}>
      <div className={compact ? "col-span-2 sm:col-span-1" : "col-span-2 lg:col-span-1"}>
        <dt className="text-xs font-medium text-zinc-500">Account value</dt>
        <dd className={`mt-2 font-medium tracking-[-0.055em] tabular-nums ${compact ? "text-3xl" : "text-[42px] leading-tight sm:text-[56px]"}`}>{capitalMoney(capital.nav)}</dd>
        <dd className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">Total cash + holdings · USD</dd>
      </div>
      <div className={compact ? "" : "lg:border-l lg:border-zinc-100 lg:pl-7 lg:dark:border-zinc-800"}>
        <dt className="text-xs font-medium text-zinc-500">Total cash</dt>
        <dd className="mt-2 text-[clamp(1rem,4.8vw,1.5rem)] font-medium tracking-tight tabular-nums">{capitalMoney(capital.cash_balance)}</dd>
        <dd className="mt-3"><dl className="space-y-1.5 text-xs">
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-zinc-500">Available</dt><dd className="font-medium tabular-nums">{capitalMoney(available)}</dd></div>
          <div className="flex flex-wrap justify-between gap-2"><dt className="text-zinc-500">Reserved</dt><dd className="tabular-nums">{capitalMoney(reserved)}</dd></div>
        </dl></dd>
      </div>
      <div className={compact ? "" : "lg:border-l lg:border-zinc-100 lg:pl-7 lg:dark:border-zinc-800"}>
        <dt className="text-xs font-medium text-zinc-500">Holdings value</dt>
        <dd className="mt-2 text-[clamp(1rem,4.8vw,1.5rem)] font-medium tracking-tight tabular-nums">{capitalMoney(capital.invested_value)}</dd>
        <dd className="mt-3 text-xs text-zinc-500">{capital.open_position_count} open position{capital.open_position_count === 1 ? "" : "s"}</dd>
        {capital.prices_as_of ? <dd className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">Prices: {new Date(capital.prices_as_of).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short" })}</dd> : null}
      </div>
    </dl>
    <details className="mt-5 text-[11px] leading-5 text-zinc-500 dark:text-zinc-400">
      <summary className="w-fit cursor-pointer hover:text-zinc-600 dark:hover:text-zinc-300">How balances work</summary>
      <p className="mt-1 max-w-2xl">Reserved cash includes order fees and is part of total cash. Available cash is unreserved; risk limits may reduce how much can be used. Holdings use the latest recorded prices.</p>
    </details>
  </div>;
}
