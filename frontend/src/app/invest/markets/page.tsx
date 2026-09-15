import Link from "next/link";
import {
  getInvestFixedIncomeProducts,
  type InvestFixedIncomeProduct,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestMarketsPage() {
  const accessToken = await getServerAccessToken();
  let fixedIncome: InvestFixedIncomeProduct[] = [];
  try {
    fixedIncome = await getInvestFixedIncomeProducts({}, { accessToken });
  } catch {
    fixedIncome = [];
  }

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <section className="grid gap-4 sm:grid-cols-2">
        <MarketCard title="United States" items={["S&P 500", "Nasdaq", "Dow", "Treasury yields"]} />
        <MarketCard title="Nigeria" items={["NGX ASI", "Banking", "Consumer", "Oil & Gas"]} />
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-500">Fixed income</p>
            <h2 className="mt-1 text-lg font-semibold">Bills, bonds, and cash yield</h2>
          </div>
          <p className="text-xs font-medium uppercase text-amber-700 dark:text-amber-300">
            Watch-only foundation
          </p>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {fixedIncome.map((product) => (
            <Link
              key={product.ticker}
              href={`/invest/fixed-income/${product.ticker}`}
              className="rounded-xl border border-zinc-200 p-4 transition hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold">{product.name}</p>
                  <p className="mt-1 text-sm text-zinc-500">
                    {product.issuer} · {product.currency}
                  </p>
                </div>
                <span className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
                  {product.market}
                </span>
              </div>
              <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
                {product.tenor} · minimum {product.currency} {product.minimum_order_amount}
              </p>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}

function MarketCard({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
