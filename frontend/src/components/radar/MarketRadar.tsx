"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import {
  addRadarWatchlistItem,
  getMarketRadarOverview,
  removeRadarWatchlistItem,
  runMarketRadarScan,
  type MarketRadarIndustry,
  type MarketRadarName,
  type MarketRadarOverview,
  type RadarWatchlistItem,
} from "@/lib/api";
import { WatchlistStrip } from "@/components/radar/WatchlistStrip";

type MarketRadarProps = {
  initialOverview: MarketRadarOverview | null;
  unavailable: boolean;
};

const dateTime = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  month: "short",
});

const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

const priceFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

export function MarketRadar({ initialOverview, unavailable }: MarketRadarProps) {
  const [overview, setOverview] = useState(initialOverview);
  const [jurisdiction, setJurisdiction] = useState<"all" | "US" | "NG">("all");
  const [scanning, setScanning] = useState(false);
  const [busyTickers, setBusyTickers] = useState<Set<string>>(new Set());

  const sessions = overview?.sessions ?? [];
  const openSessions = sessions.filter((session) => session.allows_discovery);

  const metrics = useMemo(() => {
    if (!overview) return [];
    return [
      { label: "Working set", value: String(overview.working_set_count) },
      { label: "Flagged", value: String(overview.flagged_count) },
      { label: "Industries", value: String(overview.industries.length) },
      { label: "Catalog", value: String(overview.latest_run?.catalog_count ?? 0) },
      { label: "Cache hits", value: String(overview.latest_run?.cache_hits ?? 0) },
      {
        label: "Vendor calls (last scan)",
        value: String(overview.latest_run?.vendor_calls ?? 0),
      },
    ];
  }, [overview]);

  async function reload(nextJurisdiction = jurisdiction) {
    const data = await getMarketRadarOverview(nextJurisdiction);
    setOverview(data);
  }

  async function handleScan() {
    setScanning(true);
    try {
      const jurisdictions = jurisdiction === "all" ? undefined : [jurisdiction];
      const run = await runMarketRadarScan({ jurisdictions });
      await reload();
      if (run.jurisdictions_scanned.length === 0) {
        toast.error(
          run.notes[0] || "No market is open. US and NGX vendors were not called.",
        );
      } else {
        toast.success(
          `Scanned ${run.jurisdictions_scanned.join(", ")} · ${run.vendor_calls} vendor calls · ${run.flagged_count} flagged.`,
        );
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Radar scan failed.");
    } finally {
      setScanning(false);
    }
  }

  async function handleFilter(next: "all" | "US" | "NG") {
    setJurisdiction(next);
    try {
      await reload(next);
    } catch {
      toast.error("Radar could not reload.");
    }
  }

  async function handleWatchToggle(name: MarketRadarName) {
    if (busyTickers.has(name.ticker)) return;
    const adding = !name.on_watchlist;
    setBusyTickers((current) => new Set(current).add(name.ticker));
    setOverview((current) =>
      current ? patchWatchlist(current, name, adding) : current,
    );
    try {
      if (adding) {
        await addRadarWatchlistItem({
          ticker: name.ticker,
          market: name.jurisdiction === "NG" ? "NG" : "US",
        });
        toast.success(`${name.ticker} added to watchlist.`);
      } else {
        await removeRadarWatchlistItem(name.ticker);
        toast.success(`${name.ticker} removed from watchlist.`);
      }
      await reload();
    } catch (error) {
      setOverview((current) =>
        current ? patchWatchlist(current, name, !adding) : current,
      );
      toast.error(error instanceof Error ? error.message : "Watchlist update failed.");
    } finally {
      setBusyTickers((current) => {
        const next = new Set(current);
        next.delete(name.ticker);
        return next;
      });
    }
  }

  if (!overview) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-xl font-semibold">Market Radar</h2>
        <p className="mt-2 text-sm text-zinc-500">
          {unavailable
            ? "Sign in again or refresh this page."
            : "Radar data will appear after the first scan."}
        </p>
      </section>
    );
  }

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <WatchlistStrip items={overview.watchlist ?? []} onChanged={() => reload()} />
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Discovery
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Market Radar</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Industry-grouped unusual volume, price and risk. Names you have never
              typed can still appear here.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {(["all", "US", "NG"] as const).map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => void handleFilter(key)}
                className={
                  jurisdiction === key ? buttonPrimaryClassName : buttonSecondaryClassName
                }
              >
                {key === "all" ? "All markets" : key === "US" ? "United States" : "Nigeria"}
              </button>
            ))}
            <button
              type="button"
              onClick={() => void handleScan()}
              disabled={scanning}
              className={buttonPrimaryClassName}
            >
              {scanning ? "Scanning…" : "Scan open markets"}
            </button>
          </div>
        </div>

        <div className="grid gap-3 border-b border-zinc-200 px-5 py-4 sm:grid-cols-2 dark:border-zinc-800">
          {overview.sessions.map((session) => (
            <div
              key={session.jurisdiction}
              className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50"
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-medium">
                  {session.jurisdiction === "NG" ? "Nigeria (NGX)" : "United States"}
                </p>
                <span className="text-xs text-zinc-500">{session.label}</span>
              </div>
              <p className="mt-1 text-xs text-zinc-500">
                Vendors: {session.vendors.join(", ")}
                {session.allows_discovery
                  ? " · discovery allowed"
                  : " · no API calls while closed"}
              </p>
            </div>
          ))}
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-3 sm:divide-x sm:divide-y-0 lg:grid-cols-6 dark:divide-zinc-800">
          {metrics.map((metric) => (
            <div key={metric.label} className="px-5 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                {metric.label}
              </p>
              <p className="mt-2 text-xl font-semibold tabular-nums">{metric.value}</p>
            </div>
          ))}
        </div>
      </section>

      {overview.latest_run && (
        <section className="rounded-xl border border-zinc-200 bg-white p-5 text-sm dark:border-zinc-800 dark:bg-zinc-950">
          <p className="font-medium">
            Last scan {dateTime.format(new Date(overview.latest_run.started_at))}
          </p>
          <p className="mt-1 text-zinc-500">
            Scanned {overview.latest_run.jurisdictions_scanned.join(", ") || "none"}.
            {overview.latest_run.promoted_count > 0
              ? ` Promoted ${overview.latest_run.promoted_count} name(s) to the Opportunity Queue.`
              : null}
          </p>
          {overview.latest_run.notes.map((note) => (
            <p key={note} className="mt-1 text-zinc-500">
              {note}
            </p>
          ))}
        </section>
      )}

      {openSessions.length === 0 && (
        <p className="text-sm text-zinc-500">
          Both sessions are closed. The last working set stays on screen; scanning now
          will not call US or NGX vendors.
        </p>
      )}

      {overview.scan_changes && overview.scan_changes.length > 0 ? (
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h3 className="text-sm font-semibold">Since last scan</h3>
          <p className="mt-1 text-xs text-zinc-500">
            Names that lurched versus the previous radar print, not versus yesterday.
          </p>
          <div className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-900">
            {overview.scan_changes.slice(0, 8).map((name) => (
              <NameRow
                key={`lurch-${name.ticker}`}
                name={name}
                busy={busyTickers.has(name.ticker)}
                onWatchToggle={handleWatchToggle}
              />
            ))}
          </div>
        </section>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-2">
        {overview.industries.map((industry) => (
          <IndustryCard
            key={`${industry.jurisdiction}-${industry.name}`}
            industry={industry}
            busyTickers={busyTickers}
            onWatchToggle={handleWatchToggle}
          />
        ))}
      </div>

      {overview.industries.length === 0 && (
        <section className="rounded-xl border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
          No radar snapshot yet. Scan while a market is open, or wait for the scheduled
          job (every 30 minutes, closed markets skipped).
        </section>
      )}
    </div>
  );
}

function IndustryCard({
  industry,
  busyTickers,
  onWatchToggle,
}: {
  industry: MarketRadarIndustry;
  busyTickers: Set<string>;
  onWatchToggle: (name: MarketRadarName) => void;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">{industry.name}</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {industry.name_count} names · {industry.jurisdiction}
          </p>
        </div>
        <HeatBadge heat={industry.heat} />
      </div>
      <div className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
        {industry.names.map((name) => (
          <NameRow
            key={name.ticker}
            name={name}
            busy={busyTickers.has(name.ticker)}
            onWatchToggle={onWatchToggle}
          />
        ))}
      </div>
    </section>
  );
}

function NameRow({
  name,
  busy,
  onWatchToggle,
}: {
  name: MarketRadarName;
  busy: boolean;
  onWatchToggle: (name: MarketRadarName) => void;
}) {
  const price = name.price ? priceFormat.format(Number(name.price)) : "-";
  const sourceDate = name.source_as_of
    ? dateTime.format(new Date(name.source_as_of))
    : dateTime.format(new Date(name.as_of));
  const zScore = evidenceText(name.evidence, "price_return_zscore");
  const relative = evidenceText(name.evidence, "sector_relative_return_pct");
  const benchmark = evidenceText(name.evidence, "sector_benchmark");
  const volumeRatio = name.volume_ratio ?? evidenceText(name.evidence, "volume_ratio");
  const scanState = evidenceText(name.evidence, "scan_state");
  const scanDelta = evidenceText(name.evidence, "scan_delta_change_pct");
  const href = name.on_watchlist
    ? `/watchlist/${encodeURIComponent(name.ticker)}`
    : `/ticker-analyst?ticker=${encodeURIComponent(name.ticker)}`;

  return (
    <div className="grid gap-3 py-3 sm:grid-cols-[minmax(190px,1fr)_120px_150px] sm:items-center">
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <WatchlistButton
            ticker={name.ticker}
            watched={Boolean(name.on_watchlist)}
            busy={busy}
            onClick={() => onWatchToggle(name)}
          />
          <Link href={href} className="text-sm font-medium hover:underline">
            {name.ticker}
          </Link>
        </div>
        <p className="truncate pl-8 text-xs text-zinc-500">{name.name}</p>
        <div className="mt-1 flex flex-wrap gap-1 pl-8">
          {name.carried_forward ? <Chip tone="zinc">prior session</Chip> : null}
          {name.on_watchlist ? <Chip tone="emerald">watchlist</Chip> : null}
          {name.always_watched && !name.on_watchlist ? <Chip tone="zinc">watched</Chip> : null}
          {name.flags.slice(0, 3).map((flag) => (
            <Chip key={flag} tone={flagTone(flag)}>
              {flag.replaceAll("_", " ")}
            </Chip>
          ))}
        </div>
      </div>
      <Sparkline points={name.sparkline} changePct={name.change_pct} />
      <div className="text-left text-sm tabular-nums sm:text-right">
        <p className="font-medium">
          {name.currency} {price}
        </p>
        <p className={changeClass(name.change_pct)}>
          {name.change_pct ? `${Number(name.change_pct).toFixed(1)}%` : "-"}
        </p>
        <p className="text-xs text-zinc-500">
          {name.volume ? compact.format(name.volume) : "-"} vol
        </p>
        <p className="mt-1 text-xs text-zinc-500">as of {sourceDate}</p>
      </div>
      <div className="flex flex-wrap gap-1 sm:col-span-3">
        {zScore ? <Chip tone="zinc">z {zScore}</Chip> : null}
        {relative ? (
          <Chip tone="zinc">
            vs {benchmark || "sector"} {formatNumber(relative)}%
          </Chip>
        ) : null}
        {volumeRatio ? <Chip tone="zinc">vol {formatNumber(volumeRatio)}x</Chip> : null}
        {scanState ? (
          <Chip tone="amber">
            {scanState.replaceAll("_", " ")}
            {scanDelta ? ` ${formatNumber(scanDelta)} pts` : ""}
          </Chip>
        ) : null}
        {name.stale_reason && !name.carried_forward ? (
          <Chip tone="rose">{name.stale_reason}</Chip>
        ) : null}
      </div>
    </div>
  );
}

function HeatBadge({ heat }: { heat: string }) {
  const tone =
    heat === "unusual"
      ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
      : heat === "heating"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400";
  return (
    <span className={`rounded-md px-2 py-1 text-xs font-medium capitalize ${tone}`}>
      {heat}
    </span>
  );
}

function changeClass(value: string | null) {
  const numeric = Number(value);
  if (!value || Number.isNaN(numeric) || numeric === 0) return "text-zinc-600";
  return numeric > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-rose-700 dark:text-rose-400";
}

function Sparkline({
  points,
  changePct,
}: {
  points: Array<Record<string, unknown>>;
  changePct: string | null;
}) {
  const values = points
    .map((point) => Number(point.close))
    .filter((value) => Number.isFinite(value) && value > 0);
  if (values.length < 2) {
    return <div className="h-10 rounded-md bg-zinc-50 dark:bg-zinc-900" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 118 + 1;
      const y = 37 - ((value - min) / range) * 34;
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  const numericChange = Number(changePct);
  const stroke =
    Number.isFinite(numericChange) && numericChange < 0
      ? "stroke-rose-500"
      : "stroke-emerald-500";

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 120 40"
      className="h-10 w-full rounded-md bg-zinc-50 dark:bg-zinc-900"
      preserveAspectRatio="none"
    >
      <path d={path} fill="none" className={stroke} strokeWidth="2.5" />
    </svg>
  );
}

function Chip({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "amber" | "emerald" | "rose" | "zinc";
}) {
  const className =
    tone === "rose"
      ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
      : tone === "amber"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : tone === "emerald"
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400";
  return (
    <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${className}`}>
      {children}
    </span>
  );
}

function flagTone(flag: string): "amber" | "emerald" | "rose" | "zinc" {
  if (flag.includes("risk") || flag.includes("drop")) return "rose";
  if (flag.includes("lurch") || flag.includes("volume") || flag.includes("volatility")) return "amber";
  if (flag.includes("move") || flag.includes("anomaly")) return "emerald";
  return "zinc";
}

function evidenceText(evidence: Record<string, unknown>, key: string) {
  const value = evidence[key];
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function formatNumber(value: string) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(1) : value;
}

function WatchlistButton({
  ticker,
  watched,
  busy,
  onClick,
}: {
  ticker: string;
  watched: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      title={watched ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      aria-label={watched ? `Remove ${ticker} from watchlist` : `Add ${ticker} to watchlist`}
      aria-pressed={watched}
      className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition ${
        watched
          ? "text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950"
          : "text-zinc-400 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
      } disabled:opacity-50`}
    >
      <svg viewBox="0 0 20 20" className="h-4 w-4" aria-hidden="true">
        {watched ? (
          <path
            fill="currentColor"
            d="M5 2.5A1.5 1.5 0 0 0 3.5 4v13.1a.75.75 0 0 0 1.2.6L10 14.2l5.3 3.5a.75.75 0 0 0 1.2-.6V4A1.5 1.5 0 0 0 15 2.5H5Z"
          />
        ) : (
          <path
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            d="M5.2 3.2h9.6A1.3 1.3 0 0 1 16.1 4.5v11.8a.6.6 0 0 1-.96.48L10 13.4l-5.14 3.38a.6.6 0 0 1-.96-.48V4.5A1.3 1.3 0 0 1 5.2 3.2Z"
          />
        )}
      </svg>
    </button>
  );
}

function patchWatchlist(
  overview: MarketRadarOverview,
  name: MarketRadarName,
  onWatchlist: boolean,
): MarketRadarOverview {
  const patchName = (row: MarketRadarName) =>
    row.ticker === name.ticker ? { ...row, on_watchlist: onWatchlist } : row;
  const watchlist = onWatchlist
    ? [
        watchlistItemFromName(name),
        ...overview.watchlist.filter((item) => item.ticker !== name.ticker),
      ]
    : overview.watchlist.filter((item) => item.ticker !== name.ticker);

  return {
    ...overview,
    watchlist,
    working_set: overview.working_set.map(patchName),
    flagged: overview.flagged.map(patchName),
    scan_changes: (overview.scan_changes ?? []).map(patchName),
    industries: overview.industries.map((industry) => ({
      ...industry,
      names: industry.names.map(patchName),
    })),
  };
}

function watchlistItemFromName(name: MarketRadarName): RadarWatchlistItem {
  return {
    ticker: name.ticker,
    name: name.name,
    jurisdiction: name.jurisdiction,
    notes: null,
    added_at: new Date().toISOString(),
    on_watchlist: true,
    price: name.price,
    change_pct: name.change_pct,
    volume: name.volume,
    volume_ratio: name.volume_ratio,
    anomaly_score: name.anomaly_score,
    flags: name.flags,
    evidence: name.evidence,
    sparkline: name.sparkline,
    as_of: name.as_of,
    source_as_of: name.source_as_of,
    carried_forward: name.carried_forward,
    scan_state: evidenceText(name.evidence, "scan_state"),
    scan_delta_change_pct: evidenceText(name.evidence, "scan_delta_change_pct"),
    scan_delta_price_pct: evidenceText(name.evidence, "scan_delta_price_pct"),
  };
}
