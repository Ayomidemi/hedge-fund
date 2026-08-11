"use client";

import { useLiveData } from "@/components/providers/LiveDataProvider";

const timeFormat = new Intl.DateTimeFormat("en-US", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const rateFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
});

export function LiveStatusIndicator() {
  const { connected, pricesAsOf, lastRefresh, fxRate } = useLiveData();

  return (
    <div className="flex flex-col items-end gap-0.5 text-xs text-zinc-500">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2 w-2 rounded-full ${
            connected ? "bg-emerald-500" : "bg-amber-500"
          }`}
          aria-hidden
        />
        <span className="font-medium text-zinc-700 dark:text-zinc-300">
          {connected ? "Live" : "Offline — start ./scripts/dev-backend.sh"}
        </span>
      </div>
      {lastRefresh ? (
        <span>
          Last refresh: {lastRefresh.success_count}/{lastRefresh.ticker_count}{" "}
          quotes · {lastRefresh.positions_marked} positions marked
        </span>
      ) : pricesAsOf ? (
        <span>Prices as of {timeFormat.format(new Date(pricesAsOf))}</span>
      ) : connected ? (
        <span>Waiting for first price refresh…</span>
      ) : null}
      {fxRate ? (
        <span>
          FX {fxRate.pair_label}: {rateFormat.format(Number(fxRate.rate))}{" "}
          <span className="text-zinc-400">({fxRate.source})</span>
        </span>
      ) : null}
    </div>
  );
}
