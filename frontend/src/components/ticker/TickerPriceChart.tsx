"use client";

import { useEffect, useMemo, useState, type MouseEvent } from "react";
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

type ChartPoint = {
  x: number;
  y: number;
  label: string;
  valueLabel: string;
};

const CHART_WIDTH = 1000;
const CHART_HEIGHT = 280;
const CHART_PAD = { top: 24, right: 0, bottom: 24, left: 0 };

export function TickerPriceChart({ chart, metric }: TickerPriceChartProps) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);

  useEffect(() => {
    setActiveIndex(null);
  }, [chart, metric]);

  const { points, path, stroke, width, height } = useMemo(() => {
    if (!chart) {
      return {
        points: [] as ChartPoint[],
        path: "",
        stroke: "stroke-emerald-500",
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
      };
    }

    const raw = chart.points
      .map((point) => ({
        label: point.date || (point.at ? new Date(point.at).toLocaleTimeString() : ""),
        value: Number(metric === "price" ? point.price : point.volume),
      }))
      .filter((point) => Number.isFinite(point.value) && point.value >= 0);

    if (raw.length < 2) {
      return {
        points: [] as ChartPoint[],
        path: "",
        stroke: "stroke-emerald-500",
        width: CHART_WIDTH,
        height: CHART_HEIGHT,
      };
    }

    const min = Math.min(...raw.map((point) => point.value));
    const max = Math.max(...raw.map((point) => point.value));
    const range = max - min || 1;
    const innerWidth = CHART_WIDTH - CHART_PAD.left - CHART_PAD.right;
    const innerHeight = CHART_HEIGHT - CHART_PAD.top - CHART_PAD.bottom;

    const mapped: ChartPoint[] = raw.map((point, index) => {
      const x = CHART_PAD.left + (index / Math.max(raw.length - 1, 1)) * innerWidth;
      const y =
        CHART_PAD.top + innerHeight - ((point.value - min) / range) * innerHeight;
      return {
        x,
        y,
        label: point.label,
        valueLabel:
          metric === "volume" ? compact.format(point.value) : priceFormat.format(point.value),
      };
    });

    const path = mapped
      .map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`)
      .join(" ");
    const first = raw[0].value;
    const last = raw[raw.length - 1].value;
    const stroke = last < first ? "stroke-rose-500" : "stroke-emerald-500";

    return { points: mapped, path, stroke, width: CHART_WIDTH, height: CHART_HEIGHT };
  }, [chart, metric]);

  const activePoint = activeIndex !== null ? points[activeIndex] : null;

  function handleMouseMove(event: MouseEvent<SVGSVGElement>) {
    if (!points.length) return;
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * width;
    let nearest = 0;
    let minDistance = Infinity;
    for (let index = 0; index < points.length; index += 1) {
      const distance = Math.abs(points[index].x - x);
      if (distance < minDistance) {
        minDistance = distance;
        nearest = index;
      }
    }
    setActiveIndex(nearest);
  }

  if (points.length < 2) {
    return (
      <div className="flex h-72 items-center justify-center rounded-lg bg-zinc-50 text-sm text-zinc-500 dark:bg-zinc-900">
        Not enough prints yet. Scan while the market is open, or pick a longer range.
      </div>
    );
  }

  return (
    <div>
      <div className="relative" onMouseLeave={() => setActiveIndex(null)}>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-72 w-full cursor-crosshair rounded-lg bg-zinc-50 dark:bg-zinc-900"
          role="img"
          aria-label={`${metric} chart`}
          onMouseMove={handleMouseMove}
        >
          <path d={path} fill="none" className={stroke} strokeWidth="2.5" />
          {activePoint ? (
            <>
              <line
                x1={activePoint.x}
                y1={CHART_PAD.top}
                x2={activePoint.x}
                y2={height - CHART_PAD.bottom}
                className="stroke-zinc-300 dark:stroke-zinc-700"
                strokeWidth="1"
                strokeDasharray="4 3"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r="5"
                className={`${stroke} fill-current`}
                pointerEvents="none"
              />
              <g pointerEvents="none">
                <rect
                  x={Math.min(Math.max(activePoint.x - 52, 8), width - 112)}
                  y={Math.max(8, activePoint.y - 38)}
                  width="104"
                  height="28"
                  rx="6"
                  className="fill-zinc-900/90 dark:fill-zinc-100/95"
                />
                <text
                  x={Math.min(Math.max(activePoint.x, 60), width - 60)}
                  y={Math.max(26, activePoint.y - 20)}
                  textAnchor="middle"
                  className="fill-white text-[11px] font-semibold tabular-nums dark:fill-zinc-900"
                >
                  {activePoint.valueLabel}
                </text>
              </g>
            </>
          ) : null}
        </svg>
      </div>
      <div className="mt-2 flex justify-between text-xs text-zinc-500">
        <span>{activePoint?.label ?? points[0].label}</span>
        <span>{points[points.length - 1].label}</span>
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
