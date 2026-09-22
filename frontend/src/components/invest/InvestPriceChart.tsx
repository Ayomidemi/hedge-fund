"use client";

import { useEffect, useState } from "react";
import {
  TickerPriceChart,
  chartRangeLabel,
} from "@/components/ticker/TickerPriceChart";
import { getInvestInstrumentChart, type RadarWatchlistChart } from "@/lib/api";

const RANGES = ["1m", "3m", "1y"] as const;

export function InvestPriceChart({ ticker }: { ticker: string }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>("3m");
  const [chart, setChart] = useState<RadarWatchlistChart | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void getInvestInstrumentChart(ticker, range)
      .then((data) => {
        if (!cancelled) setChart(data);
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setChart(null);
          setError(reason instanceof Error ? reason.message : "Chart could not load.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, range]);

  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold">Price</h3>
          <p className="mt-1 text-sm text-zinc-500">
            Daily marks from stored bars, filled from Tiingo when the tape is thin.
          </p>
        </div>
        <div className="flex gap-1">
          {RANGES.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setRange(value)}
              className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
                range === value
                  ? "bg-emerald-800 text-white"
                  : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
              }`}
            >
              {chartRangeLabel(value)}
            </button>
          ))}
        </div>
      </div>
      <div className="mt-4">
        {loading ? (
          <p className="text-sm text-zinc-500">Loading chart…</p>
        ) : error ? (
          <p className="text-sm text-zinc-500">{error}</p>
        ) : (
          <TickerPriceChart chart={chart} metric="price" />
        )}
      </div>
      {chart?.note ? (
        <p className="mt-3 text-xs text-zinc-500">{chart.note}</p>
      ) : null}
    </section>
  );
}
