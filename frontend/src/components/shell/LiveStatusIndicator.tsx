"use client";

import { useLiveData } from "@/components/providers/LiveDataProvider";

export function LiveStatusIndicator() {
  const { connected, pricesAsOf, lastRefresh, fxRate } = useLiveData();
  const detail = [
    lastRefresh ? `${lastRefresh.success_count}/${lastRefresh.ticker_count} quotes refreshed · ${lastRefresh.positions_marked} positions valued` : pricesAsOf ? `Prices as of ${new Date(pricesAsOf).toLocaleTimeString()}` : "Waiting for a price refresh",
    fxRate ? `${fxRate.pair_label}: ${Number(fxRate.rate).toLocaleString()} (${fxRate.source})` : null,
  ].filter(Boolean).join(" · ");
  return <div title={detail} className="flex items-center gap-2 text-[11px] text-zinc-500">
    <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-amber-500"}`} />
    <span>{connected ? "Market data connected" : "Market data disconnected"}</span>
  </div>;
}
