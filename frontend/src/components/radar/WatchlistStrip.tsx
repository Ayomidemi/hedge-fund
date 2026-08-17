"use client";

import Link from "next/link";
import { useState } from "react";
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

type WatchlistStripProps = {
  items: RadarWatchlistItem[];
  onChanged: () => Promise<void> | void;
};

export function WatchlistStrip({ items, onChanged }: WatchlistStripProps) {
  const [ticker, setTicker] = useState("");
  const [market, setMarket] = useState<TickerMarket>("US");
  const [saving, setSaving] = useState(false);

  async function handleAdd() {
    if (!ticker.trim()) return;
    setSaving(true);
    try {
      await addRadarWatchlistItem({ ticker, market });
      setTicker("");
      toast.success(`${ticker.toUpperCase()} added to watchlist.`);
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add ticker.");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove(symbol: string) {
    try {
      await removeRadarWatchlistItem(symbol);
      toast.success(`${symbol} removed from watchlist.`);
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not remove ticker.");
    }
  }

  return (
    <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Manual list
          </p>
          <h3 className="mt-1 text-lg font-semibold">Watchlist radar</h3>
          <p className="mt-1 text-sm text-zinc-500">
            You choose the names. Radar keeps watching them. This is not the
            Opportunity Queue.
          </p>
        </div>
        <Link href="/watchlist" className={buttonSecondaryClassName}>
          Open watchlist
        </Link>
      </div>

      <div className="flex flex-wrap items-end gap-3 px-5 py-4">
        <div className="min-w-[260px] flex-1">
          <TickerSelector
            market={market}
            onMarketChange={setMarket}
            value={ticker}
            onTickerChange={setTicker}
            fetchDetailsOnSelect={false}
            placeholder="Add a ticker to watch"
          />
        </div>
        <button
          type="button"
          onClick={() => void handleAdd()}
          disabled={saving || !ticker.trim()}
          className={buttonPrimaryClassName}
        >
          {saving ? "Adding…" : "Watch"}
        </button>
      </div>

      {items.length === 0 ? (
        <p className="px-5 pb-5 text-sm text-zinc-500">
          Empty. Add a name from a radar row or type a ticker above.
        </p>
      ) : (
        <div className="flex gap-3 overflow-x-auto px-5 pb-5">
          {items.map((item) => (
            <article
              key={item.ticker}
              className="min-w-[180px] rounded-lg border border-zinc-200 bg-zinc-50 p-3 dark:border-zinc-800 dark:bg-zinc-900/60"
            >
              <div className="flex items-start justify-between gap-2">
                <Link
                  href={`/watchlist/${encodeURIComponent(item.ticker)}`}
                  className="text-sm font-semibold hover:underline"
                >
                  {item.ticker}
                </Link>
                <button
                  type="button"
                  onClick={() => void handleRemove(item.ticker)}
                  className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
                >
                  Remove
                </button>
              </div>
              <p className="mt-1 truncate text-xs text-zinc-500">{item.name}</p>
              <p className={`mt-2 text-sm tabular-nums ${changeClass(item.change_pct)}`}>
                {item.price ? priceFormat.format(Number(item.price)) : "—"}
                {item.change_pct
                  ? ` · ${Number(item.change_pct) > 0 ? "+" : ""}${Number(item.change_pct).toFixed(1)}%`
                  : ""}
              </p>
              {item.scan_state ? (
                <p className="mt-1 text-[11px] capitalize text-zinc-500">
                  {item.scan_state.replaceAll("_", " ")}
                </p>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function changeClass(value: string | null) {
  const numeric = Number(value);
  if (!value || Number.isNaN(numeric) || numeric === 0) return "text-zinc-600";
  return numeric > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-rose-700 dark:text-rose-400";
}
