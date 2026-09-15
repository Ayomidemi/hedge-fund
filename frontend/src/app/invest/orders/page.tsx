import Link from "next/link";
import { getInvestOrders, type InvestOrder } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";
import { money } from "@/components/invest/format";

export default async function InvestOrdersPage() {
  const accessToken = await getServerAccessToken();
  let orders: InvestOrder[] = [];
  try {
    orders = await getInvestOrders({ accessToken });
  } catch {
    orders = [];
  }

  if (orders.length === 0) {
    return (
      <div className="mx-auto max-w-3xl rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        No orders yet.
      </div>
    );
  }

  return (
    <ul className="mx-auto max-w-3xl divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      {orders.map((order) => (
        <li key={order.id} className="p-4">
          <Link href={`/invest/orders/${order.id}`} className="font-semibold hover:underline">
            {order.side} {order.ticker}
          </Link>
          <p className="mt-1 text-sm text-zinc-500">
            {order.status}
            {order.average_fill_price ? ` · filled at ${money(order.average_fill_price)}` : ""}
            {order.notional ? ` · ${money(order.notional)}` : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}
