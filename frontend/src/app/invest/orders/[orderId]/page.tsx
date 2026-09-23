import Link from "next/link";
import { InvestOrderActions } from "@/components/invest/InvestOrderActions";
import { money } from "@/components/invest/format";
import { getInvestOrder, type InvestOrder } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestOrderDetailPage({
  params,
}: {
  params: Promise<{ orderId: string }>;
}) {
  const { orderId } = await params;
  const accessToken = await getServerAccessToken();
  let order: InvestOrder | null = null;

  try {
    order = await getInvestOrder(orderId, { accessToken });
  } catch {
    order = null;
  }

  if (!order) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Order could not be loaded.
      </div>
    );
  }

  return (
    <div className="w-full space-y-4">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-sm text-zinc-500">{order.name}</p>
        <h2 className="mt-1 text-2xl font-semibold">
          {order.side} {order.ticker}
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          {order.status} · {order.order_type.toUpperCase()}
        </p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <Detail
            label="Notional"
            value={order.notional ? money(order.notional, order.currency) : "-"}
          />
          <Detail label="Requested quantity" value={order.quantity ?? "-"} />
          <Detail label="Filled quantity" value={order.filled_quantity ?? "-"} />
          <Detail
            label="Average fill"
            value={order.average_fill_price ? money(order.average_fill_price, order.currency) : "-"}
          />
          <Detail label="Broker" value={order.broker_provider ?? "-"} />
          <Detail label="Broker ref" value={order.broker_order_id ?? "-"} />
          <Detail
            label="Submitted"
            value={new Date(order.submitted_at).toLocaleString()}
          />
          <Detail
            label="Filled"
            value={order.filled_at ? new Date(order.filled_at).toLocaleString() : "-"}
          />
        </div>
        {order.warnings.length > 0 ? (
          <ul className="mt-5 space-y-2 text-sm text-amber-700 dark:text-amber-300">
            {order.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        ) : null}
        <div className="mt-5 flex flex-wrap gap-2">
          <Link
            href="/invest/portfolio"
            className="inline-flex items-center justify-center rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            Back to portfolio
          </Link>
          <InvestOrderActions orderId={order.id} status={order.status} />
          <Link
            href={hrefForOrder(order)}
            className="inline-flex items-center justify-center rounded-xl border border-zinc-200 bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            Open asset
          </Link>
        </div>
      </section>
    </div>
  );
}

function hrefForOrder(order: InvestOrder) {
  if (order.asset_class === "bond" || order.asset_class === "cash_equivalent") {
    return `/invest/fixed-income/${order.ticker}`;
  }
  return `/invest/instruments/${order.ticker}`;
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">{value}</p>
    </div>
  );
}
