"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "@/components/ui/ToastProvider";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import {
  addRadarWatchlistItem,
  removeRadarWatchlistItem,
  type RadarWatchlistItem,
} from "@/lib/api";
import type { TickerMarket } from "@/lib/ticker-prefill-form";

const priceFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

type WatchlistDeskProps = {
  initialItems: RadarWatchlistItem[];
  unavailable: boolean;
};

export function WatchlistDesk({ initialItems, unavailable }: WatchlistDeskProps) {
  const [items, setItems] = useState(initialItems);
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState<TickerMarket>("US");
  const [saving, setSaving] = useState(false);

  const sorted = useMemo(
    () =>
      [...items].sort((left, right) => {
        const leftMove = Math.abs(Number(left.change_pct ?? 0));
        const rightMove = Math.abs(Number(right.change_pct ?? 0));
        return rightMove - leftMove;
      }),
    [items],
  );

  async function handleAdd() {
    if (!ticker.trim()) return;
    setSaving(true);
    try {
      const item = await addRadarWatchlistItem({ ticker, market });
      setItems((current) => [
        item,
        ...current.filter((row) => row.ticker !== item.ticker),
      ]);
      setTicker("");
      toast.success(`${item.ticker} is on the watchlist.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add ticker.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(symbol: string) {
    try {
      await removeRadarWatchlistItem(symbol);
      setItems((current) => current.filter((row) => row.ticker !== symbol));
      toast.success(`${symbol} removed.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not remove ticker.");
    }
  }

  if (unavailable && items.length === 0) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-xl font-semibold">Watchlist</h2>
        <p className="mt-2 text-sm text-zinc-500">Sign in again or refresh this page.</p>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Lookout
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Watchlist</h2>
          <p className="mt-1 max-w-2xl text-sm text-zinc-500">
            A manual list of names you want on the tape. Radar watches movement
            against yesterday, against the name&apos;s own history, and against the
            last scan. Nothing here is a buy.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3 px-5 py-4">
          <div className="min-w-[280px] flex-1">
            <TickerSelector
              market={market}
              onMarketChange={setMarket}
              value={ticker}
              onTickerChange={setTicker}
              fetchDetailsOnSelect={false}
              placeholder="AAPL or GTCO"
            />
          </div>
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={saving || !ticker.trim()}
            className={buttonPrimaryClassName}
          >
            {saving ? "Adding…" : "Add to watchlist"}
          </button>
          <Link href="/market-radar" className={buttonSecondaryClassName}>
            Back to radar
          </Link>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        {sorted.length === 0 ? (
          <p className="p-8 text-center text-sm text-zinc-500">
            The list is empty. Add a ticker, or star one from Market Radar.
          </p>
        ) : (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {sorted.map((item) => (
              <div
                key={item.ticker}
                className="grid gap-3 px-5 py-4 sm:grid-cols-[minmax(160px,1.2fr)_1fr_1fr_auto] sm:items-center"
              >
                <div className="min-w-0">
                  <Link
                    href={`/watchlist/${encodeURIComponent(item.ticker)}`}
                    className="text-sm font-semibold hover:underline"
                  >
                    {item.ticker}
                  </Link>
                  <p className="truncate text-xs text-zinc-500">{item.name}</p>
                  <p className="mt-1 text-[11px] uppercase tracking-wide text-zinc-400">
                    {item.jurisdiction}
                  </p>
                </div>
                <ClockCell
                  label="vs yesterday"
                  value={
                    item.change_pct
                      ? `${Number(item.change_pct) > 0 ? "+" : ""}${Number(item.change_pct).toFixed(1)}%`
                      : "—"
                  }
                  tone={item.change_pct}
                />
                <ClockCell
                  label="vs last radar"
                  value={
                    item.scan_state
                      ? `${item.scan_state.replaceAll("_", " ")}${
                          item.scan_delta_change_pct
                            ? ` · ${Number(item.scan_delta_change_pct) > 0 ? "+" : ""}${Number(item.scan_delta_change_pct).toFixed(1)} pts`
                            : ""
                        }`
                      : "—"
                  }
                  tone={item.scan_delta_change_pct}
                />
                <div className="flex items-center justify-end gap-2">
                  <p className="text-sm tabular-nums">
                    {item.price ? priceFormat.format(Number(item.price)) : "—"}
                  </p>
                  <button
                    type="button"
                    onClick={() => void handleRemove(item.ticker)}
                    className={buttonSecondaryClassName}
                  >
                    Remove
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function ClockCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: string | null;
}) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className={`mt-1 text-sm capitalize ${changeClass(tone)}`}>{value}</p>
    </div>
  );
}

function changeClass(value: string | null) {
  const numeric = Number(value);
  if (!value || Number.isNaN(numeric) || numeric === 0) return "text-zinc-700 dark:text-zinc-300";
  return numeric > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-rose-700 dark:text-rose-400";
}
