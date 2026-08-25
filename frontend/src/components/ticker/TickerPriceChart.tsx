"use client";

import { useMemo } from "react";
import type { RadarWatchlistChart } from "@/lib/api";

const priceFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

type TickerPriceChartProps = {
  chart: RadarWatchlistChart | null;
  metric: "price" | "volume";
};

export function TickerPriceChart({ chart, metric }: TickerPriceChartProps) {
  const values = useMemo(() => {
    if (!chart) return [];
    return chart.points
      .map((point) => ({
        label: point.date || (point.at ? new Date(point.at).toLocaleTimeString() : ""),
        value: Number(metric === "price" ? point.price : point.volume),
      }))
      .filter((point) => Number.isFinite(point.value) && point.value >= 0);
  }, [chart, metric]);

  if (values.length < 2) {
    return (
      <div className="flex h-64 items-center justify-center rounded-lg bg-zinc-50 text-sm text-zinc-500 dark:bg-zinc-900">
        Not enough prints yet. Scan while the market is open, or pick a longer range.
      </div>
    );
  }

  const min = Math.min(...values.map((point) => point.value));
  const max = Math.max(...values.map((point) => point.value));
  const range = max - min || 1;
  const width = 720;
  const height = 260;
  const pad = 16;
  const path = values
    .map((point, index) => {
      const x = pad + (index / Math.max(values.length - 1, 1)) * (width - pad * 2);
      const y = height - pad - ((point.value - min) / range) * (height - pad * 2);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const first = values[0].value;
  const last = values[values.length - 1].value;
  const stroke = last < first ? "stroke-rose-500" : "stroke-emerald-500";

  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-64 w-full rounded-lg bg-zinc-50 dark:bg-zinc-900"
        role="img"
        aria-label={`${metric} chart`}
      >
        <path d={path} fill="none" className={stroke} strokeWidth="2.5" />
      </svg>
      <div className="mt-2 flex justify-between text-xs text-zinc-500">
        <span>{values[0].label}</span>
        <span className="tabular-nums">
          {metric === "volume" ? compact.format(last) : priceFormat.format(last)}
        </span>
        <span>{values[values.length - 1].label}</span>
      </div>
    </div>
  );
}

export function chartRangeLabel(range: string) {
  if (range === "1d") return "today's scans";
  if (range === "1m") return "1 month";
  if (range === "3m") return "3 months";
  if (range === "1y") return "1 year";
  return "5 years";
}
