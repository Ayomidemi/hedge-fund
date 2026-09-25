import Link from "next/link";
import type {
  InvestMarketQuote,
  InvestMarkets,
  InvestSearchDefaults,
} from "@/lib/api";
import { money, signedPercent } from "@/components/invest/format";
import { InvestSearch } from "@/components/invest/InvestSearch";
import { InvestFixedIncomeShelf } from "@/components/invest/InvestFixedIncomeShelf";

export function InvestMarketsBoard({
  markets,
  searchConfig,
}: {
  markets: InvestMarkets;
  searchConfig?: InvestSearchDefaults;
}) {
  const openSessions = markets.sessions.filter((session) => session.is_open);
  const listedCount = markets.boards.reduce(
    (total, board) => total + board.items.length,
    0,
  );

  return (
    <div className="w-full space-y-4">
      <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_420px] sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Markets
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              Fixed income and listed market context
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {markets.summary}
            </p>
            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <HeaderMetric
                label="Open sessions"
                value={openSessions.length ? String(openSessions.length) : "0"}
                detail={
                  openSessions.length
                    ? openSessions.map((session) => session.market).join(", ")
                    : "Cash markets shut"
                }
              />
              <HeaderMetric
                label="Fixed income"
                value={String(markets.fixed_income.length)}
                detail="Bills and bonds"
              />
              <HeaderMetric
                label="Listed tape"
                value={String(listedCount)}
                detail="ETFs and market pulses"
              />
            </div>
          </div>
          <div className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Search
            </p>
            <div className="mt-3">
              <InvestSearch
                initialMarket={searchConfig?.default_market}
                initialQuery=""
                markets={searchConfig?.markets}
                variant="embedded"
              />
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 border-t border-zinc-100 px-5 py-3 dark:border-zinc-900 sm:px-6">
          {markets.sessions.map((session) => (
            <span
              key={session.market}
              className={`rounded-md px-2 py-1 text-xs font-medium ${
                session.is_open
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
                  : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
              }`}
            >
              {session.label}
            </span>
          ))}
        </div>
      </section>

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.75fr)]">
        <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <div className="border-b border-zinc-100 p-5 dark:border-zinc-900 sm:p-6">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Fixed income
                </p>
                <h2 className="mt-1 text-lg font-semibold">Yield shelf</h2>
              </div>
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-500">
              Bills and bonds show yield, clean price, accrued interest, dirty
              price, settlement, and projected payout before order entry.
            </p>
          </div>
          <div className="p-5 sm:p-6">
            <InvestFixedIncomeShelf products={markets.fixed_income} />
          </div>
        </section>

        <ListedTapePanel boards={markets.boards} />
      </div>
    </div>
  );
}

function HeaderMetric({
  detail,
  label,
  value,
}: {
  detail: string;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-900">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 truncate text-xs text-zinc-500">{detail}</p>
    </div>
  );
}

function ListedTapePanel({
  boards,
}: {
  boards: InvestMarkets["boards"];
}) {
  return (
    <aside className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-100 p-5 dark:border-zinc-900">
        <div className="flex items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Listed tape
            </p>
            <h2 className="mt-1 text-lg font-semibold">Proxies and pulses</h2>
          </div>
          <p className="text-xs font-medium uppercase text-emerald-700 dark:text-emerald-300">
            Paper-tradable
          </p>
        </div>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          ETF proxies and listed market context stay beside the yield shelf.
        </p>
      </div>

      <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
        {boards.map((board) => (
          <section key={board.id} className="p-5">
            <div>
              <h3 className="text-sm font-semibold">{board.title}</h3>
              <p className="mt-1 text-xs leading-5 text-zinc-500">
                {board.description}
              </p>
            </div>
            <ul className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-900">
              {board.items.map((item) => (
                <MarketRow key={item.ticker} item={item} />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </aside>
  );
}

function MarketRow({ item }: { item: InvestMarketQuote }) {
  const changeClass =
    Number(item.change_pct) > 0
      ? "text-emerald-700 dark:text-emerald-300"
      : Number(item.change_pct) < 0
        ? "text-red-700 dark:text-red-300"
        : "text-zinc-500";

  return (
    <li>
      <Link
        href={item.href}
        className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-900"
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold">
            {item.label}{" "}
            <span className="font-medium text-zinc-500">{item.ticker}</span>
          </p>
          <p className="truncate text-xs text-zinc-500">{item.name}</p>
        </div>
        <div className="text-right">
          <p className="text-sm font-semibold tabular-nums">
            {item.price ? money(item.price, item.currency) : "—"}
          </p>
          <p className={`text-xs tabular-nums ${changeClass}`}>
            {signedPercent(item.change_pct)} · {statusLabel(item.quote_status)}
          </p>
        </div>
      </Link>
    </li>
  );
}

function statusLabel(status: string) {
  if (status === "live") return "live";
  if (status === "last_close") return "last close";
  return "no mark";
}
