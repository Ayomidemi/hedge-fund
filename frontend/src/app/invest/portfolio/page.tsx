import Link from "next/link";
import { getInvestHome, type InvestHome } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";
import { money, signedMoney, signedPercent } from "@/components/invest/format";

export default async function InvestPortfolioPage() {
  const accessToken = await getServerAccessToken();
  let home: InvestHome | null = null;
  try {
    home = await getInvestHome({ accessToken });
  } catch {
    home = null;
  }

  if (!home) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        Portfolio could not be loaded.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Stat label="Total" value={money(home.portfolio_value)} />
        <Stat label="Cash" value={money(home.cash)} />
        <Stat label="Allocated" value={money(home.invested)} />
        <Stat
          label="Total return"
          value={`${signedMoney(home.total_return)} ${
            home.total_return_pct ? `(${signedPercent(home.total_return_pct)})` : ""
          }`}
        />
        <Stat label="Positions" value={String(home.holdings.length)} />
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-lg font-semibold">Allocation</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {home.allocation.map((bucket) => (
            <div key={bucket.name} className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {bucket.name}
              </p>
              <p className="mt-1 font-semibold tabular-nums">
                {money(bucket.value)}
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                {Number(bucket.allocation_pct).toFixed(2)}%
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        {home.holdings.length === 0 ? (
          <p className="p-6 text-sm text-zinc-500">
            No paper positions yet. <Link href="/invest/markets" className="underline">Review fixed income</Link>{" "}
            before using the listed-instrument paper loop.
          </p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Asset</th>
                <th className="px-4 py-3">Class</th>
                <th className="px-4 py-3">Qty</th>
                <th className="px-4 py-3">Weight</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Return</th>
              </tr>
            </thead>
            <tbody>
              {home.holdings.map((holding) => (
                <tr key={holding.ticker} className="border-t border-zinc-100 dark:border-zinc-900">
                  <td className="px-4 py-3">
                    <Link href={holding.href ?? `/invest/instruments/${holding.ticker}`} className="font-semibold">
                      {holding.ticker}
                    </Link>
                    <p className="text-xs text-zinc-500">{holding.name}</p>
                  </td>
                  <td className="px-4 py-3 capitalize text-zinc-500">
                    {(holding.asset_class ?? "-").replaceAll("_", " ")}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{Number(holding.quantity).toFixed(4)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {holding.allocation_pct ? `${Number(holding.allocation_pct).toFixed(2)}%` : "-"}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{money(holding.market_value, holding.currency)}</td>
                  <td className="px-4 py-3 tabular-nums">
                    {signedMoney(holding.unrealized_pnl)}
                    {holding.unrealized_pnl_pct
                      ? ` (${signedPercent(holding.unrealized_pnl_pct)})`
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}
