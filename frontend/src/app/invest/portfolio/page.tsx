import Link from "next/link";
import { InvestAccountSummary } from "@/components/invest/InvestAccountSummary";
import { connection } from "next/server";
import { getInvestHome, getInvestOrders, type InvestHome, type InvestOrder } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";
import { money, signedMoney, signedPercent } from "@/components/invest/format";

export default async function InvestPortfolioPage({
  searchParams,
}: {
  searchParams: Promise<{ placed?: string }>;
}) {
  await connection();
  const params = await searchParams;
  const accessToken = await getServerAccessToken();
  let home: InvestHome | null = null;
  let orders: InvestOrder[] = [];
  const [homeResult, ordersResult] = await Promise.allSettled([
    getInvestHome({ accessToken }), getInvestOrders({ accessToken }),
  ]);
  home = homeResult.status === "fulfilled" ? homeResult.value : null;
  orders = ordersResult.status === "fulfilled" ? ordersResult.value : [];

  if (!home) {
    return (
      <div className="rounded-sm border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        Portfolio could not be loaded.
      </div>
    );
  }

  const rows = portfolioRows(home.holdings, orders, params.placed);

  return (
    <div className="w-full space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="mb-2 text-xs text-stone-500">Your account</p><h2 className="text-3xl sm:text-4xl">Portfolio.</h2></div><Link href="/invest/markets" className="text-sm underline underline-offset-4">Explore investments ↗</Link></div>
      <InvestAccountSummary home={home} />

      <section className="rounded-sm border border-stone-300/70 bg-[#fffefb] p-6 dark:border-zinc-800 dark:bg-[#151613]">
        <h2 className="text-lg font-semibold">Allocation</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {home.allocation.map((bucket) => (
            <div key={bucket.name} className="rounded-sm bg-zinc-50 p-4 dark:bg-zinc-900">
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {bucket.name}
              </p>
              <p className="mt-1 font-semibold tabular-nums">
                {money(bucket.value, home.account.base_currency)}
              </p>
              <p className="mt-1 text-xs text-zinc-500">
                {Number(bucket.allocation_pct).toFixed(2)}%
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-sm border border-stone-300/70 bg-[#fffefb] dark:border-zinc-800 dark:bg-[#151613]">
        <h2 className="px-4 pt-5 text-lg font-semibold">Holdings &amp; orders</h2>
        {rows.length === 0 ? (
          <p className="p-6 pt-3 text-sm text-zinc-500">
            No orders yet. <Link href="/invest/markets" className="underline">Review fixed income</Link>{" "}
            to compare available investments.
          </p>
        ) : (
          <div className="overflow-x-auto"><table className="w-full min-w-[680px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3">Asset</th>
                <th className="px-4 py-3">Last order</th>
                <th className="px-4 py-3">Qty</th>
                <th className="px-4 py-3">Weight</th>
                <th className="px-4 py-3">Value</th>
                <th className="px-4 py-3">Return</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={`border-t border-zinc-100 dark:border-zinc-900 ${
                    row.highlight ? "bg-emerald-50 dark:bg-emerald-950/40" : ""
                  }`}
                >
                  <td className="px-4 py-3">
                    <Link href={row.href} className="font-semibold hover:underline">
                      {row.ticker}
                    </Link>
                    <p className="text-xs text-zinc-500">{row.name}</p>
                  </td>
                  <td className="px-4 py-3">
                    {row.order ? (
                      <>
                        <Link
                          href={`/invest/orders/${row.order.id}`}
                          className="font-medium capitalize hover:underline"
                        >
                          {row.order.side.toLowerCase()} · {row.order.status.toLowerCase()}
                        </Link>
                        <p className="text-xs text-zinc-500">
                          {new Date(row.order.submitted_at).toLocaleString()}
                        </p>
                      </>
                    ) : (
                      <span className="text-zinc-500">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 tabular-nums">{row.quantity}</td>
                  <td className="px-4 py-3 tabular-nums">{row.weight}</td>
                  <td className="px-4 py-3 tabular-nums">{row.value}</td>
                  <td className="px-4 py-3 tabular-nums">{row.pnl}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </section>
    </div>
  );
}

function portfolioRows(
  holdings: InvestHome["holdings"],
  orders: InvestOrder[],
  placed: string | undefined,
) {
  const latestOrder = new Map<string, InvestOrder>();
  for (const order of orders) {
    if (!latestOrder.has(order.ticker)) {
      latestOrder.set(order.ticker, order);
    }
  }

  const used = new Set<string>();
  const rows = holdings.map((holding) => {
    used.add(holding.ticker);
    const order = latestOrder.get(holding.ticker) ?? null;
    return {
      key: holding.ticker,
      ticker: holding.ticker,
      name: holding.name,
      href: holding.href ?? `/invest/instruments/${holding.ticker}`,
      quantity: Number(holding.quantity).toFixed(4),
      weight: holding.allocation_pct
        ? `${Number(holding.allocation_pct).toFixed(2)}%`
        : "—",
      value: money(holding.market_value, holding.currency),
      pnl: `${signedMoney(holding.unrealized_pnl, holding.currency)}${
        holding.unrealized_pnl_pct
          ? ` (${signedPercent(holding.unrealized_pnl_pct)})`
          : ""
      }`,
      order,
      highlight: order !== null && placed === order.id,
    };
  });

  for (const order of orders) {
    if (used.has(order.ticker)) continue;
    used.add(order.ticker);
    rows.push({
      key: order.id,
      ticker: order.ticker,
      name: order.name,
      href: `/invest/orders/${order.id}`,
      quantity: String(order.filled_quantity ?? order.quantity ?? "—"),
      weight: "—",
      value: order.notional ? money(order.notional, order.currency) : "—",
      pnl: "—",
      order,
      highlight: placed === order.id,
    });
  }

  return rows;
}
