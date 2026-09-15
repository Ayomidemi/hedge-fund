import Link from "next/link";
import {
  getInvestFixedIncomeProduct,
  type InvestFixedIncomeProduct,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestFixedIncomeDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const accessToken = await getServerAccessToken();
  let product: InvestFixedIncomeProduct | null = null;

  try {
    product = await getInvestFixedIncomeProduct(ticker, { accessToken });
  } catch {
    product = null;
  }

  if (!product) {
    return (
      <div className="mx-auto max-w-3xl rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Fixed-income product could not be loaded.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-sm text-zinc-500">{product.issuer}</p>
        <h2 className="mt-1 text-2xl font-semibold">{product.name}</h2>
        <p className="mt-2 text-sm text-zinc-500">
          {product.instrument_type.replaceAll("_", " ")} · {product.market} · {product.currency}
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Detail label="Tenor" value={product.tenor} />
          <Detail label="Maturity" value={product.maturity_date ?? "Issue dependent"} />
          <Detail
            label="Indicative yield"
            value={product.indicative_yield_pct ? `${product.indicative_yield_pct}%` : "Pending provider"}
          />
          <Detail
            label="Minimum"
            value={`${product.currency} ${product.minimum_order_amount}`}
          />
          <Detail label="Liquidity" value={product.liquidity} />
          <Detail label="Risk" value={product.risk_level} />
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h3 className="text-lg font-semibold">Expected payout</h3>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {product.expected_payout}
        </p>
        <ul className="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          {product.retail_notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        <div className="mt-5 flex flex-wrap gap-2">
          <span className="inline-flex items-center rounded-xl bg-amber-50 px-4 py-2.5 text-sm font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-200">
            {product.trade_status.replaceAll("_", " ")}
          </span>
          <Link
            href="/invest/markets"
            className="inline-flex items-center justify-center rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            Back to markets
          </Link>
        </div>
      </section>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold capitalize tabular-nums">{value}</p>
    </div>
  );
}
