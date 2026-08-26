"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { WatchlistButton } from "@/components/radar/WatchlistButton";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  inputControlClassName,
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
import { tickerHubPath } from "@/lib/ticker-hub-path";

type MarketRadarProps = {
  initialOverview: MarketRadarOverview | null;
  unavailable: boolean;
};

type FocusTab = "promote" | "desk" | "lurch";

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
  const [focusTab, setFocusTab] = useState<FocusTab>("promote");

  const openSessions = (overview?.sessions ?? []).filter(
    (session) => session.allows_discovery,
  );

  const focusLists = useMemo(() => {
    if (!overview) {
      return { promote: [] as MarketRadarName[], desk: [], lurch: [] };
    }
    return {
      promote: overview.queue_candidates ?? [],
      desk: overview.desk_alerts ?? [],
      lurch: (overview.scan_changes ?? []).slice(0, 8),
    };
  }, [overview]);

  const hasFocus =
    focusLists.promote.length > 0 ||
    focusLists.desk.length > 0 ||
    focusLists.lurch.length > 0;

  useEffect(() => {
    if (focusLists[focusTab].length > 0) return;
    if (focusLists.promote.length > 0) {
      setFocusTab("promote");
      return;
    }
    if (focusLists.desk.length > 0) {
      setFocusTab("desk");
      return;
    }
    if (focusLists.lurch.length > 0) setFocusTab("lurch");
  }, [focusLists, focusTab]);

  const activeFocus = focusLists[focusTab];

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
        <p className="text-sm text-zinc-500">
          {unavailable
            ? "Sign in again or refresh this page."
            : "Radar data will appear after the first scan."}
        </p>
      </section>
    );
  }

  const run = overview.latest_run;
  const sessionSummary = overview.sessions
    .map((session) => {
      const market = session.jurisdiction === "NG" ? "NGX" : "US";
      return `${market} ${session.label.toLowerCase()}`;
    })
    .join(" · ");

  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-zinc-500">
            {[
              sessionSummary,
              `${overview.flagged_count} flagged`,
              overview.p0_count || overview.p1_count
                ? `${overview.p0_count ?? 0} P0 · ${overview.p1_count ?? 0} P1`
                : null,
              run
                ? `Last scan ${dateTime.format(new Date(run.started_at))}`
                : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </p>
          {openSessions.length === 0 ? (
            <p className="mt-1 text-xs text-zinc-500">
              Markets closed — last working set stays on screen; scanning will not call
              vendors.
            </p>
          ) : null}
          {run?.promoted_count ? (
            <p className="mt-1 text-xs text-zinc-500">
              Auto-promoted {run.promoted_count} P0/P1 name
              {run.promoted_count === 1 ? "" : "s"} to the Opportunity Queue.
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2">
            <select
              aria-label="Market filter"
              value={jurisdiction}
              onChange={(event) =>
                void handleFilter(event.target.value as "all" | "US" | "NG")
              }
              className={`${inputControlClassName} w-auto min-w-[10.5rem] py-2.5`}
            >
              <option value="all">All markets</option>
              <option value="US">United States</option>
              <option value="NG">Nigeria</option>
            </select>
            <button
              type="button"
              onClick={() => void handleScan()}
              disabled={scanning}
              className={buttonPrimaryClassName}
            >
              {scanning ? "Scanning…" : "Scan"}
            </button>
          </div>
        </div>
      </header>

      {hasFocus ? (
        <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
            <div>
              <h3 className="text-sm font-semibold">Focus</h3>
              <p className="mt-0.5 text-xs text-zinc-500">{focusHint(focusTab)}</p>
            </div>
            <div className="flex flex-wrap gap-1">
              {(
                [
                  {
                    key: "promote" as const,
                    label: "P0 / P1",
                    count: focusLists.promote.length,
                  },
                  {
                    key: "desk" as const,
                    label: "Held & watched",
                    count: focusLists.desk.length,
                  },
                  {
                    key: "lurch" as const,
                    label: "Since scan",
                    count: focusLists.lurch.length,
                  },
                ] as const
              )
                .filter((tab) => tab.count > 0)
                .map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setFocusTab(tab.key)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                      focusTab === tab.key
                        ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
                        : "text-zinc-500 hover:bg-zinc-100 hover:text-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
                    }`}
                  >
                    {tab.label}
                    <span className="ml-1.5 tabular-nums opacity-70">{tab.count}</span>
                  </button>
                ))}
            </div>
          </div>
          <div className="divide-y divide-zinc-100 px-5 dark:divide-zinc-900">
            {activeFocus.length ? (
              activeFocus.map((name) => (
                <NameRow
                  key={`${focusTab}-${name.ticker}`}
                  name={name}
                  busy={busyTickers.has(name.ticker)}
                  onWatchToggle={handleWatchToggle}
                  compact
                />
              ))
            ) : (
              <p className="py-6 text-sm text-zinc-500">
                Nothing in this focus list right now.
              </p>
            )}
          </div>
        </section>
      ) : null}

      <div>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold">By industry</h3>
          <p className="text-xs text-zinc-500">
            {overview.working_set_count} names · {overview.industries.length} groups
          </p>
        </div>
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
        {overview.industries.length === 0 ? (
          <section className="rounded-xl border border-zinc-200 bg-white p-8 text-center text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
            No radar snapshot yet. Scan while a market is open, or wait for the scheduled
            job (every 30 minutes, closed markets skipped).
          </section>
        ) : null}
      </div>
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
  const status = industry.status ?? "quiet";
  const median = industry.median_change_pct
    ? `${Number(industry.median_change_pct) > 0 ? "+" : ""}${Number(industry.median_change_pct).toFixed(1)}%`
    : null;

  return (
    <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between gap-3 border-b border-zinc-100 px-4 py-3 dark:border-zinc-900">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold">{industry.name}</h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            {industry.jurisdiction}
            {median ? ` · ${median} median` : ""}
            {` · ${industry.flagged_count}/${industry.name_count} flagged`}
          </p>
        </div>
        <HeatBadge heat={industry.heat} label={industryStatusLabel(status)} />
      </div>
      <div className="divide-y divide-zinc-100 px-4 dark:divide-zinc-900">
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
  compact = false,
}: {
  name: MarketRadarName;
  busy: boolean;
  onWatchToggle: (name: MarketRadarName) => void;
  compact?: boolean;
}) {
  const price =
    name.price != null && name.price !== "" && Number.isFinite(Number(name.price))
      ? priceFormat.format(Number(name.price))
      : "—";
  const moveScope = evidenceText(name.evidence, "move_scope");
  const scanState = evidenceText(name.evidence, "scan_state");
  const scanDelta = evidenceText(name.evidence, "scan_delta_change_pct");
  const href = tickerHubPath(name.ticker);
  const detail = secondaryDetail(name);

  return (
    <div
      className={`grid gap-x-3 gap-y-1.5 py-2.5 sm:items-center ${
        compact
          ? "grid-cols-[minmax(0,1fr)_5.5rem]"
          : "grid-cols-[minmax(0,1fr)_5.5rem] sm:grid-cols-[minmax(0,1fr)_5.5rem_5.5rem]"
      }`}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-1">
          <WatchlistButton
            ticker={name.ticker}
            watched={Boolean(name.on_watchlist)}
            busy={busy}
            onClick={() => onWatchToggle(name)}
          />
          <Link href={href} className="text-sm font-medium hover:underline">
            {name.ticker}
          </Link>
          {name.radar_priority ? (
            <Chip tone={priorityTone(name.radar_priority)}>{name.radar_priority}</Chip>
          ) : null}
          <CareChip name={name} />
          {moveScope && moveScope !== "none" ? <MoveScopeChip scope={moveScope} /> : null}
          {scanState && scanState !== "steady" ? (
            <Chip tone="amber">
              {scanState.replaceAll("_", " ")}
              {scanDelta ? ` ${formatNumber(scanDelta)}` : ""}
            </Chip>
          ) : null}
        </div>
        <p className="truncate pl-8 text-xs text-zinc-500">
          {name.name}
          {detail ? ` · ${detail}` : ""}
        </p>
      </div>
      {!compact ? (
        <div className="hidden sm:block">
          <Sparkline points={name.sparkline} changePct={name.change_pct} />
        </div>
      ) : null}
      <div className="shrink-0 text-right tabular-nums">
        <p className="text-sm font-medium">{price}</p>
        <p className={`text-xs ${changeClass(name.change_pct)}`}>
          {name.change_pct != null &&
          name.change_pct !== "" &&
          Number.isFinite(Number(name.change_pct))
            ? `${Number(name.change_pct) > 0 ? "+" : ""}${Number(name.change_pct).toFixed(1)}%`
            : "—"}
        </p>
      </div>
    </div>
  );
}

function focusHint(tab: FocusTab) {
  if (tab === "promote") {
    return "Highest-priority movers that auto-enter (or should enter) the Opportunity Queue.";
  }
  if (tab === "desk") {
    return "Names you already hold or watch that moved enough to notice, but not enough for auto-queue.";
  }
  return "Names that lurched versus the previous radar print — not versus yesterday.";
}

function secondaryDetail(name: MarketRadarName) {
  const relative = evidenceText(name.evidence, "sector_relative_return_pct");
  const volumeRatio = name.volume_ratio ?? evidenceText(name.evidence, "volume_ratio");
  const parts: string[] = [];
  if (relative) {
    const numeric = Number(relative);
    if (Number.isFinite(numeric)) {
      parts.push(`vs sector ${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`);
    }
  }
  if (volumeRatio) {
    const numeric = Number(volumeRatio);
    if (Number.isFinite(numeric) && numeric >= 1.5) {
      parts.push(`${numeric.toFixed(1)}x vol`);
    }
  } else if (name.volume) {
    parts.push(`${compact.format(name.volume)} vol`);
  }
  if (name.carried_forward) parts.push("prior session");
  return parts.slice(0, 2).join(" · ");
}

function HeatBadge({ heat, label }: { heat: string; label?: string }) {
  const tone =
    heat === "unusual"
      ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
      : heat === "heating"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400";
  return (
    <span className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${tone}`}>
      {label ?? heat}
    </span>
  );
}

function industryStatusLabel(status: string) {
  if (status === "market_event") return "Market event";
  if (status === "industry_event") return "Industry event";
  if (status === "isolated_names") return "Isolated names";
  return "Quiet";
}

function MoveScopeChip({ scope }: { scope: string | null }) {
  if (scope === "isolated") return <Chip tone="amber">isolated</Chip>;
  if (scope === "industry") return <Chip tone="rose">industry</Chip>;
  if (scope === "market") return <Chip tone="rose">market</Chip>;
  return null;
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
    return <div className="h-8 rounded-md bg-zinc-50 dark:bg-zinc-900" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const path = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 86 + 1;
      const y = 30 - ((value - min) / range) * 26;
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
      viewBox="0 0 88 32"
      className="h-8 w-full rounded-md bg-zinc-50 dark:bg-zinc-900"
      preserveAspectRatio="none"
    >
      <path d={path} fill="none" className={stroke} strokeWidth="2" />
    </svg>
  );
}

function priorityTone(priority: string): "amber" | "emerald" | "rose" | "zinc" {
  if (priority === "P0") return "rose";
  if (priority === "P1") return "amber";
  if (priority === "P2") return "emerald";
  return "zinc";
}

function CareChip({ name }: { name: MarketRadarName }) {
  const flagged = name.flags.length > 0 || Boolean(name.radar_priority);
  const tier = name.care_tier;
  if (tier === "position") {
    return <Chip tone="rose">{flagged ? "held alert" : "held"}</Chip>;
  }
  if (tier === "watchlist" || name.on_watchlist) {
    if (!flagged || tier !== "watchlist") return null;
    return <Chip tone="emerald">watched alert</Chip>;
  }
  if (tier === "queue" && flagged) {
    return <Chip tone="amber">queue</Chip>;
  }
  return null;
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

function evidenceText(evidence: Record<string, unknown>, key: string) {
  const value = evidence[key];
  if (value === null || value === undefined || value === "") return null;
  return String(value);
}

function formatNumber(value: string) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric.toFixed(1) : value;
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
    queue_candidates: (overview.queue_candidates ?? []).map(patchName),
    desk_alerts: (overview.desk_alerts ?? []).map(patchName),
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
