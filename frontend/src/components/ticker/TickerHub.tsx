"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { WatchlistButton } from "@/components/radar/WatchlistButton";
import { TickerPriceChart, chartRangeLabel } from "@/components/ticker/TickerPriceChart";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import {
  addRadarWatchlistItem,
  createTickerTriage,
  getTickerChart,
  getTickerDesk,
  refreshTickerNews,
  removeRadarWatchlistItem,
  type RadarWatchlistChart,
  type TickerDesk,
} from "@/lib/api";
import { tickerMarketFromSymbol } from "@/lib/ticker-hub-path";

const CHART_RANGES = ["1d", "1m", "3m", "1y", "5y"] as const;
const NEWS_PAGE_SIZE = 5;
const queueStatusLabels: Record<string, string> = {
  discovered: "Discovered",
  screening: "Screening",
  research: "Research",
  watchlist: "Hold in queue",
  candidate: "Candidate",
  approved: "Approved",
  active_position: "Active Position",
  exited: "Exited",
  post_mortem: "Post-Mortem",
  rejected: "Rejected",
};

const priceFormat = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});
const dateTime = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

type TickerHubProps = {
  ticker: string;
  initialDesk: TickerDesk | null;
  initialChart: RadarWatchlistChart | null;
  unavailable: boolean;
};

export function TickerHub({
  ticker,
  initialDesk,
  initialChart,
  unavailable,
}: TickerHubProps) {
  const [desk, setDesk] = useState(initialDesk);
  const [chart, setChart] = useState(initialChart);
  const [range, setRange] = useState<(typeof CHART_RANGES)[number]>("1d");
  const [metric, setMetric] = useState<"price" | "volume">("price");
  const [loadingChart, setLoadingChart] = useState(false);
  const [loadingDesk, setLoadingDesk] = useState(false);
  const [watchlistBusy, setWatchlistBusy] = useState(false);
  const [refreshingNews, setRefreshingNews] = useState(false);
  const [runningTriage, setRunningTriage] = useState(false);
  const [newsPage, setNewsPage] = useState(0);
  const market = tickerMarketFromSymbol(ticker);

  useEffect(() => {
    setDesk(initialDesk);
    setChart(initialChart);
    setNewsPage(0);
  }, [initialDesk, initialChart, ticker]);

  useEffect(() => {
    if (range === "1d" && initialChart?.range === "1d") {
      setChart(initialChart);
      return;
    }
    setLoadingChart(true);
    void getTickerChart(ticker, range)
      .then(setChart)
      .catch(() => toast.error("Chart could not load."))
      .finally(() => setLoadingChart(false));
  }, [initialChart, range, ticker]);

  async function reloadDesk() {
    setLoadingDesk(true);
    try {
      setDesk(await getTickerDesk(ticker));
    } catch {
      toast.error("Ticker desk could not be loaded.");
    } finally {
      setLoadingDesk(false);
    }
  }

  async function handleWatchToggle() {
    setWatchlistBusy(true);
    try {
      if (desk?.on_watchlist) {
        await removeRadarWatchlistItem(ticker);
        toast.success(`${ticker} removed from watchlist.`);
      } else {
        await addRadarWatchlistItem({ ticker, market });
        toast.success(`${ticker} added to watchlist.`);
      }
      await reloadDesk();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Watchlist update failed.");
    } finally {
      setWatchlistBusy(false);
    }
  }

  async function handleRefreshNews() {
    setRefreshingNews(true);
    try {
      await refreshTickerNews(ticker, { market });
      await reloadDesk();
      setNewsPage(0);
      toast.success("News refreshed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "News refresh failed.");
    } finally {
      setRefreshingNews(false);
    }
  }

  async function handleQuickTriage() {
    setRunningTriage(true);
    try {
      await createTickerTriage(ticker, { market });
      await reloadDesk();
      toast.success("Quick triage saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Quick triage failed.");
    } finally {
      setRunningTriage(false);
    }
  }

  if (unavailable) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-xl font-semibold">{ticker}</h2>
        <p className="mt-2 text-sm text-zinc-500">Sign in again or refresh this page.</p>
      </section>
    );
  }

  if (!desk) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mt-1 flex items-center gap-2">
          <h2 className="text-xl font-semibold">{ticker}</h2>
          <WatchlistButton
            ticker={ticker}
            watched={false}
            busy={watchlistBusy}
            onClick={() => void handleWatchToggle()}
          />
        </div>
        <p className="mt-2 text-sm text-zinc-500">
          No desk data yet. Run a market scan or add this name to your watchlist.
        </p>
        <div className="mt-4">
          <Link href="/market-radar" className={buttonSecondaryClassName}>
            Market Radar
          </Link>
        </div>
      </section>
    );
  }

  const radar = desk.radar;
  const headlines = desk.recent_headlines?.length
    ? desk.recent_headlines
    : desk.news
      ? [desk.news]
      : [];
  const newsPageCount = Math.max(1, Math.ceil(headlines.length / NEWS_PAGE_SIZE));
  const safeNewsPage = Math.min(newsPage, newsPageCount - 1);
  const pagedHeadlines = headlines.slice(
    safeNewsPage * NEWS_PAGE_SIZE,
    safeNewsPage * NEWS_PAGE_SIZE + NEWS_PAGE_SIZE,
  );

  return (
    <div className="mx-auto max-w-[1180px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Ticker
            </p>
            <div className="mt-1 flex items-center gap-2">
              <h2 className="text-2xl font-semibold tracking-tight">{desk.ticker}</h2>
              <WatchlistButton
                ticker={desk.ticker}
                watched={desk.on_watchlist}
                busy={watchlistBusy || loadingDesk}
                onClick={() => void handleWatchToggle()}
              />
            </div>
            <p className="mt-1 text-sm text-zinc-500">
              {desk.name}
              {desk.jurisdiction ? ` · ${desk.jurisdiction}` : ""}
              {desk.exchange ? ` · ${desk.exchange}` : ""}
            </p>
            <div className="mt-3 flex flex-wrap items-baseline gap-3">
              <p className="text-2xl font-semibold tabular-nums">
                {radar?.price ? priceFormat.format(Number(radar.price)) : "—"}
              </p>
              <p className={`text-sm font-medium tabular-nums ${changeClass(radar?.change_pct)}`}>
                {formatPct(radar?.change_pct)}
              </p>
              {radar?.as_of ? (
                <p className="text-xs text-zinc-500">as of {dateTime.format(new Date(radar.as_of))}</p>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {desk.in_portfolio ? <StatusChip label="Position" tone="rose" /> : null}
              {desk.on_watchlist ? <StatusChip label="Watchlist" tone="amber" /> : null}
              {desk.opportunity ? (
                <StatusChip
                  label={queueStatusLabels[desk.opportunity.status] ?? desk.opportunity.status}
                  tone="sky"
                />
              ) : null}
              {radar?.radar_priority ? (
                <StatusChip label={radar.radar_priority} tone="zinc" />
              ) : null}
              {radar?.move_scope && radar.move_scope !== "none" ? (
                <StatusChip label={formatScope(radar.move_scope)} tone="rose" />
              ) : null}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/ticker-analyst?analyze=${encodeURIComponent(desk.ticker)}&workflow=1`}
              className={buttonPrimaryClassName}
            >
              Full analysis
            </Link>
            <button
              type="button"
              onClick={() => void handleQuickTriage()}
              disabled={runningTriage || loadingDesk}
              className={buttonSecondaryClassName}
            >
              {runningTriage ? "Running…" : desk.latest_triage ? "Refresh triage" : "Quick triage"}
            </button>
          </div>
        </div>

        {desk.decision_snapshot ? (
          <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Decision
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <h3 className="text-lg font-semibold">{desk.decision_snapshot.action_label}</h3>
              <StatusChip label={formatLabel(desk.decision_snapshot.stance)} tone="zinc" />
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {desk.decision_snapshot.summary}
            </p>
            {desk.decision_snapshot.next_step ? (
              <p className="mt-2 text-sm text-zinc-500">{desk.decision_snapshot.next_step}</p>
            ) : null}
          </div>
        ) : null}

        <div className="grid gap-px bg-zinc-200 sm:grid-cols-2 lg:grid-cols-4 dark:bg-zinc-800">
          <FactCard
            label="vs yesterday"
            value={formatPct(radar?.change_pct)}
            hint="Latest radar print."
          />
          <FactCard
            label="vs sector"
            value={
              radar?.sector_relative_return_pct
                ? `${Number(radar.sector_relative_return_pct) > 0 ? "+" : ""}${Number(radar.sector_relative_return_pct).toFixed(1)}%`
                : "—"
            }
            hint={radar?.sector ? `${radar.sector} context` : "Sector residual when available."}
          />
          <FactCard
            label="Since last scan"
            value={scanLabel(radar)}
            hint="Intraday lurch versus the prior radar print."
          />
          <FactCard
            label="Book"
            value={
              desk.position
                ? `${desk.position.quantity} @ ${priceFormat.format(Number(desk.position.average_cost))}`
                : "No live position"
            }
            hint={
              desk.pre_trade
                ? `Pre-trade: ${desk.pre_trade.decision} · ${desk.pre_trade.risk_level}`
                : "No recent pre-trade check."
            }
          />
        </div>
      </section>

      <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">
              {metric === "price" ? "Price" : "Volume"} · {chartRangeLabel(range)}
            </h3>
            <p className="mt-1 text-xs text-zinc-500">
              {range === "1d"
                ? "Same-day radar film: each scan is a frame. Hover a point for its price."
                : "Daily bars from stored history. Hover a point for its price."}
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
            {CHART_RANGES.map((key) => (
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
            <TickerPriceChart chart={chart} metric={metric} />
          )}
        </div>
        {chart?.note ? <p className="mt-3 text-xs text-zinc-500">{chart.note}</p> : null}
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold">News</h3>
              <p className="mt-1 text-xs text-zinc-500">
                Stored headlines linked to {desk.ticker}. Refresh pulls a fresh ticker feed.
              </p>
            </div>
            <RefreshIconButton
              busy={refreshingNews}
              label="Refresh news"
              onClick={() => void handleRefreshNews()}
            />
          </div>
          {headlines.length ? (
            <>
              <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
                {pagedHeadlines.map((item) => (
                  <li key={item.id} className="py-3 first:pt-0">
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sm font-medium hover:underline"
                      >
                        {item.title}
                      </a>
                    ) : (
                      <p className="text-sm font-medium">{item.title}</p>
                    )}
                    <p className="mt-1 text-xs text-zinc-500">
                      {[item.source_name, item.published_at ? dateTime.format(new Date(item.published_at)) : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
              {headlines.length > NEWS_PAGE_SIZE ? (
                <div className="mt-4 flex items-center justify-between gap-3 border-t border-zinc-100 pt-3 dark:border-zinc-900">
                  <p className="text-xs text-zinc-500">
                    {safeNewsPage * NEWS_PAGE_SIZE + 1}–
                    {Math.min((safeNewsPage + 1) * NEWS_PAGE_SIZE, headlines.length)} of{" "}
                    {headlines.length}
                  </p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={safeNewsPage === 0}
                      onClick={() => setNewsPage((page) => Math.max(0, page - 1))}
                      className={buttonSecondaryClassName}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      disabled={safeNewsPage >= newsPageCount - 1}
                      onClick={() =>
                        setNewsPage((page) => Math.min(newsPageCount - 1, page + 1))
                      }
                      className={buttonSecondaryClassName}
                    >
                      Next
                    </button>
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <p className="mt-4 text-sm text-zinc-500">
              No stored headlines for this ticker yet. Refresh news or wait for the next poll to
              tag it.
            </p>
          )}
        </section>

        <section className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
          <h3 className="text-sm font-semibold">Tape context</h3>
          <dl className="mt-4 space-y-3 text-sm">
            <Row label="Industry" value={radar?.industry ?? radar?.sector ?? "—"} />
            <Row
              label="Move scope"
              value={radar?.move_scope ? formatScope(radar.move_scope) : "—"}
            />
            <Row
              label="Industry state"
              value={radar?.industry_status ? formatLabel(radar.industry_status) : "—"}
            />
            <Row label="Volume ratio" value={radar?.volume_ratio ?? "—"} />
            <Row label="Return z" value={radar?.price_return_zscore ?? "—"} />
            <Row
              label="Flags"
              value={radar?.flags?.length ? radar.flags.map(formatLabel).join(", ") : "—"}
            />
            <Row
              label="Latest triage"
              value={
                desk.latest_triage
                  ? `${desk.latest_triage.action_label} · ${dateTime.format(new Date(desk.latest_triage.generated_at))}`
                  : "Not run"
              }
            />
          </dl>
          {desk.memos.length ? (
            <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Memos</p>
              <ul className="mt-2 space-y-2">
                {desk.memos.slice(0, 3).map((memo) => (
                  <li key={memo.id}>
                    <Link
                      href={`/ticker-analyst?analyze=${encodeURIComponent(memo.ticker)}`}
                      className="text-sm hover:underline"
                    >
                      {memo.classification || memo.ticker} · {memo.memo_date}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

function RefreshIconButton({
  busy,
  label,
  onClick,
}: {
  busy: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={busy}
      title={label}
      aria-label={label}
      className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-zinc-500 transition hover:bg-zinc-100 hover:text-zinc-800 disabled:opacity-50 dark:hover:bg-zinc-900 dark:hover:text-zinc-100"
    >
      <svg
        viewBox="0 0 20 20"
        className={`h-4 w-4 ${busy ? "animate-spin" : ""}`}
        aria-hidden="true"
      >
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
          d="M10 3.5a6.5 6.5 0 1 1-5.2 2.6M4.5 4.5v3h3"
        />
      </svg>
    </button>
  );
}

function FactCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="bg-white px-5 py-4 dark:bg-zinc-950">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-2 text-lg font-semibold capitalize">{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{hint}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

function StatusChip({
  label,
  tone,
}: {
  label: string;
  tone: "rose" | "amber" | "sky" | "zinc";
}) {
  const toneClass =
    tone === "rose"
      ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
      : tone === "amber"
        ? "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : tone === "sky"
          ? "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-300"
          : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400";
  return (
    <span className={`rounded-md px-2 py-0.5 text-xs font-medium ${toneClass}`}>{label}</span>
  );
}

function formatPct(value: string | null | undefined) {
  if (!value) return "—";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "—";
  return `${numeric > 0 ? "+" : ""}${numeric.toFixed(1)}%`;
}

function scanLabel(radar: TickerDesk["radar"]) {
  if (!radar) return "—";
  const state = radar.scan_state ? formatLabel(radar.scan_state) : "moved";
  if (!radar.scan_delta_change_pct) return state;
  const numeric = Number(radar.scan_delta_change_pct);
  if (!Number.isFinite(numeric)) return state;
  return `${state} · ${numeric > 0 ? "+" : ""}${numeric.toFixed(1)} pts`;
}

function formatScope(scope: string) {
  if (scope === "isolated") return "isolated";
  if (scope === "industry") return "industry-wide";
  if (scope === "market") return "market-wide";
  return formatLabel(scope);
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function changeClass(value: string | null | undefined) {
  const numeric = Number(value);
  if (!value || !Number.isFinite(numeric) || numeric === 0) return "text-zinc-600";
  return numeric > 0
    ? "text-emerald-700 dark:text-emerald-400"
    : "text-rose-700 dark:text-rose-400";
}
