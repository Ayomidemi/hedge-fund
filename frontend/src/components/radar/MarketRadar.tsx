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
  getMarketRadarOverview,
  runMarketRadarScan,
  type MarketRadarIndustry,
  type MarketRadarName,
  type MarketRadarOverview,
} from "@/lib/api";

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

      <div className="grid gap-4 xl:grid-cols-2">
        {overview.industries.map((industry) => (
          <IndustryCard key={`${industry.jurisdiction}-${industry.name}`} industry={industry} />
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

function IndustryCard({ industry }: { industry: MarketRadarIndustry }) {
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
          <NameRow key={name.ticker} name={name} />
        ))}
      </div>
    </section>
  );
}

function NameRow({ name }: { name: MarketRadarName }) {
  const price = name.price ? priceFormat.format(Number(name.price)) : "-";
  const sourceDate = name.source_as_of
    ? dateTime.format(new Date(name.source_as_of))
    : dateTime.format(new Date(name.as_of));
  const zScore = evidenceText(name.evidence, "price_return_zscore");
  const relative = evidenceText(name.evidence, "sector_relative_return_pct");
  const benchmark = evidenceText(name.evidence, "sector_benchmark");
  const volumeRatio = name.volume_ratio ?? evidenceText(name.evidence, "volume_ratio");

  return (
    <div className="grid gap-3 py-3 sm:grid-cols-[minmax(170px,1fr)_120px_150px] sm:items-center">
      <div className="min-w-0">
        <Link
          href={`/ticker-analyst?ticker=${encodeURIComponent(name.ticker)}`}
          className="text-sm font-medium hover:underline"
        >
          {name.ticker}
        </Link>
        <p className="truncate text-xs text-zinc-500">{name.name}</p>
        <div className="mt-1 flex flex-wrap gap-1">
          {name.carried_forward ? <Chip tone="zinc">prior session</Chip> : null}
          {name.always_watched ? <Chip tone="zinc">watched</Chip> : null}
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
  if (flag.includes("volume") || flag.includes("volatility")) return "amber";
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
