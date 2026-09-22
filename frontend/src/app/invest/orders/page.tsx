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
      <div className="w-full rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        No orders yet.
      </div>
    );
  }

  return (
    <ul className="w-full divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      {orders.map((order) => (
        <li
          key={order.id}
          className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div>
            <Link href={`/invest/orders/${order.id}`} className="font-semibold hover:underline">
              {order.side} {order.ticker}
            </Link>
            <p className="mt-1 text-sm text-zinc-500">{order.name}</p>
            <p className="mt-1 text-xs capitalize text-zinc-500">
              {order.status.toLowerCase()} · {order.order_type} ·{" "}
              {new Date(order.submitted_at).toLocaleString()}
            </p>
          </div>
          <div className="text-sm tabular-nums sm:text-right">
            <p className="font-medium">
              {order.notional ? money(order.notional, order.currency) : "-"}
            </p>
            <p className="text-zinc-500">
              {order.filled_quantity ?? order.quantity ?? "-"} units
              {order.average_fill_price
                ? ` at ${money(order.average_fill_price, order.currency)}`
                : ""}
            </p>
          </div>
        </li>
      ))}
    </ul>
  );
}
