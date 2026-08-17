"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import {
  getRadarWatchlistChart,
  removeRadarWatchlistItem,
  type RadarWatchlistChart,
  type RadarWatchlistDetail,
} from "@/lib/api";

const RANGES = ["1d", "1m", "3m", "1y", "5y"] as const;
const priceFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

type WatchlistTickerProps = {
  ticker: string;
  initialDetail: RadarWatchlistDetail | null;
  initialChart: RadarWatchlistChart | null;
  unavailable: boolean;
};

export function WatchlistTicker({
  ticker,
  initialDetail,
  initialChart,
  unavailable,
}: WatchlistTickerProps) {
  const [detail, setDetail] = useState(initialDetail);
  const [chart, setChart] = useState(initialChart);
  const [range, setRange] = useState<(typeof RANGES)[number]>("1d");
  const [metric, setMetric] = useState<"price" | "volume">("price");
  const [loadingChart, setLoadingChart] = useState(false);

  useEffect(() => {
    if (range === "1d" && initialChart?.range === "1d") {
      setChart(initialChart);
      return;
    }
    setLoadingChart(true);
    void getRadarWatchlistChart(ticker, range)
      .then(setChart)
      .catch(() => toast.error("Chart could not load."))
      .finally(() => setLoadingChart(false));
  }, [initialChart, range, ticker]);

  async function handleRemove() {
    try {
      await removeRadarWatchlistItem(ticker);
      toast.success(`${ticker} removed from watchlist.`);
      setDetail(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not remove ticker.");
    }
  }

  if (!detail) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-xl font-semibold">{ticker}</h2>
        <p className="mt-2 text-sm text-zinc-500">
          {unavailable
            ? "Sign in again or refresh this page."
            : "This ticker is not on the watchlist."}
        </p>
        <Link href="/watchlist" className={`${buttonSecondaryClassName} mt-4`}>
          Back to watchlist
        </Link>
      </section>
    );
  }

  const clocks = [
    {
      title: "vs yesterday",
      body: formatPct(detail.clocks.vs_yesterday?.change_pct ?? detail.change_pct),
      hint: "Session move against the prior close.",
    },
    {
      title: "vs own history",
      body: detail.clocks.vs_own_history?.price_return_zscore
        ? `z ${String(detail.clocks.vs_own_history.price_return_zscore)}`
        : "—",
      hint: volumeHint(detail.clocks.vs_own_history),
    },
    {
      title: "vs last radar",
      body: scanBody(detail),
      hint: minutesHint(detail.clocks.vs_last_radar?.scan_minutes_since_prior),
    },
  ];

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Watchlist
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">{detail.ticker}</h2>
            <p className="mt-1 text-sm text-zinc-500">
              {detail.name} · {detail.jurisdiction}
            </p>
            <p className="mt-2 text-lg font-semibold tabular-nums">
              {detail.price ? priceFormat.format(Number(detail.price)) : "—"}
              <span className={`ml-2 text-sm ${changeClass(detail.change_pct)}`}>
                {formatPct(detail.change_pct)}
              </span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/ticker-analyst?ticker=${encodeURIComponent(detail.ticker)}`}
              className={buttonSecondaryClassName}
            >
              Ticker Analyst
            </Link>
            <Link href="/watchlist" className={buttonSecondaryClassName}>
              All names
            </Link>
            <button type="button" onClick={() => void handleRemove()} className={buttonPrimaryClassName}>
              Remove
            </button>
          </div>
        </div>
        <div className="grid gap-px bg-zinc-200 sm:grid-cols-3 dark:bg-zinc-800">
          {clocks.map((clock) => (
            <div key={clock.title} className="bg-white px-5 py-4 dark:bg-zinc-950">
              <p className="text-[11px] uppercase tracking-wide text-zinc-500">
                {clock.title}
              </p>
              <p className="mt-2 text-lg font-semibold capitalize">{clock.body}</p>
              <p className="mt-1 text-xs text-zinc-500">{clock.hint}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">
              {metric === "price" ? "Price" : "Volume"} · {rangeLabel(range)}
            </h3>
            <p className="mt-1 text-xs text-zinc-500">
              {range === "1d"
                ? "Same-day radar film: each scan is a frame."
                : "Daily bars. US names may fill from Tiingo if history is thin; NGX uses stored bars only."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(["price", "volume"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setMetric(key)}
                className={metric === key ? buttonPrimaryClassName : buttonSecondaryClassName}
              >
                {key === "price" ? "Price" : "Volume"}
              </button>
            ))}
            {RANGES.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => setRange(key)}
                className={range === key ? buttonPrimaryClassName : buttonSecondaryClassName}
              >
                {key.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4">
          {loadingChart ? (
            <p className="text-sm text-zinc-500">Loading chart…</p>
          ) : (
            <WatchlistChart chart={chart} metric={metric} />
          )}
        </div>
        {chart?.note ? <p className="mt-3 text-xs text-zinc-500">{chart.note}</p> : null}
        {chart?.filled_from_vendor ? (
          <p className="mt-1 text-xs text-zinc-500">Filled missing history from Tiingo.</p>
        ) : null}
      </section>
    </div>
  );
}

function WatchlistChart({
  chart,
  metric,
}: {
  chart: RadarWatchlistChart | null;
  metric: "price" | "volume";
}) {
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

function formatPct(value: string | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function scanBody(detail: RadarWatchlistDetail) {
  const state = detail.clocks.vs_last_radar?.scan_state || detail.scan_state;
  const delta = detail.clocks.vs_last_radar?.scan_delta_change_pct ?? detail.scan_delta_change_pct;
  if (!state && (delta === null || delta === undefined)) return "—";
  const stateText = state ? String(state).replaceAll("_", " ") : "moved";
  if (delta === null || delta === undefined || delta === "") return stateText;
  const numeric = Number(delta);
  if (!Number.isFinite(numeric)) return stateText;
  return `${stateText} · ${numeric > 0 ? "+" : ""}${numeric.toFixed(1)} pts`;
}

function volumeHint(clock?: RadarWatchlistDetail["clocks"][string]) {
  if (!clock) return "Unusual versus this name's recent tape.";
  const bits = [];
  if (clock.volume_zscore) bits.push(`vol z ${String(clock.volume_zscore)}`);
  if (clock.volatility_ratio) bits.push(`vol ratio ${String(clock.volatility_ratio)}`);
  return bits.join(" · ") || "Unusual versus this name's recent tape.";
}

function minutesHint(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "Did this name lurch since the last scan?";
  return `${numeric} minutes since the last radar print.`;
}

function rangeLabel(range: string) {
  if (range === "1d") return "today's scans";
  if (range === "1m") return "1 month";
  if (range === "3m") return "3 months";
  if (range === "1y") return "1 year";
  return "5 years";
}

function changeClass(value: string | null) {
  const numeric = Number(value);
  if (!value || Number.isNaN(numeric) || numeric === 0) return "text-zinc-600";
  return numeric > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-rose-700 dark:text-rose-400";
}
