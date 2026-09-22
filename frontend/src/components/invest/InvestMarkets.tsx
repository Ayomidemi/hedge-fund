import Link from "next/link";
import type { InvestMarketQuote, InvestMarkets } from "@/lib/api";
import { money, signedPercent } from "@/components/invest/format";
import { InvestSearch } from "@/components/invest/InvestSearch";
import { InvestFixedIncomeShelf } from "@/components/invest/InvestFixedIncomeShelf";

export function InvestMarketsBoard({ markets }: { markets: InvestMarkets }) {
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Markets</p>
        <h2 className="mt-1 text-2xl font-semibold">Live tape, listed proxies</h2>
        <p className="mt-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          {markets.summary}
        </p>
        <div className="mt-5">
          <InvestSearch initialQuery="" variant="embedded" />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
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

      {markets.boards.map((board) => (
        <section
          key={board.id}
          className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">{board.title}</h2>
              <p className="mt-1 text-sm text-zinc-500">{board.description}</p>
            </div>
            <p className="text-xs font-medium uppercase text-emerald-800 dark:text-emerald-300">
              Paper-tradable
            </p>
          </div>
          <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
            {board.items.map((item) => (
              <MarketRow key={item.ticker} item={item} />
            ))}
          </ul>
        </section>
      ))}

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-500">Fixed income</p>
            <h2 className="mt-1 text-lg font-semibold">Yield shelf</h2>
          </div>
          <p className="text-xs font-medium uppercase text-emerald-700 dark:text-emerald-300">
            Modeled paper orders
          </p>
        </div>
        <p className="mt-2 text-sm text-zinc-500">
          Bills and bonds show modeled yield, clean price, accrued interest, dirty
          price, settlement, and projected payout before you place a paper order.
        </p>
        <div className="mt-4">
          <InvestFixedIncomeShelf products={markets.fixed_income} />
        </div>
      </section>
    </div>
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
        className="flex items-center justify-between gap-3 py-3 hover:bg-zinc-50 dark:hover:bg-zinc-900"
      >
        <div>
          <p className="font-semibold">
            {item.label}{" "}
            <span className="font-medium text-zinc-500">{item.ticker}</span>
          </p>
          <p className="text-xs text-zinc-500">{item.name}</p>
        </div>
        <div className="text-right">
          <p className="tabular-nums font-semibold">
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
