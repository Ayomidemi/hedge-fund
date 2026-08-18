"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import { useLiveData } from "@/components/providers/LiveDataProvider";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import {
  getNewsOverview,
  pollNews,
  refreshTickerNews,
  type NewsItem,
  type NewsOverview,
  type NewsPagination,
} from "@/lib/api";
import type { TickerMarket } from "@/lib/ticker-prefill-form";

type NewsCentreProps = {
  initialOverview: NewsOverview | null;
  initialJurisdiction: "all" | "US" | "NG";
  unavailable: boolean;
};

const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const CURRENT_PAGE_SIZE = 20;

export function NewsCentre({
  initialOverview,
  initialJurisdiction,
  unavailable,
}: NewsCentreProps) {
  const [overview, setOverview] = useState(initialOverview);
  const [market, setMarket] = useState<TickerMarket>(
    initialOverview?.ticker?.endsWith(".NG") ? "NG" : "US",
  );
  const [ticker, setTicker] = useState(initialOverview?.ticker ?? "");
  const [jurisdiction, setJurisdiction] =
    useState<"all" | "US" | "NG">(initialJurisdiction);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const { lastNewsPoll } = useLiveData();

  async function reload(next?: {
    ticker?: string;
    market?: TickerMarket;
    jurisdiction?: "all" | "US" | "NG";
    page?: number;
  }) {
    const nextTicker = next?.ticker ?? overview?.ticker ?? "";
    const nextMarket = next?.market ?? market;
    const nextJurisdiction = next?.jurisdiction ?? jurisdiction;
    const nextPage = next?.page ?? overview?.current_page.page ?? 1;
    const data = await getNewsOverview({
      ticker: nextTicker || undefined,
      market: nextTicker ? nextMarket : undefined,
      jurisdiction: nextJurisdiction,
      page: nextPage,
      page_size: CURRENT_PAGE_SIZE,
    });
    setOverview(data);
  }

  async function handleFilter(next: "all" | "US" | "NG") {
    setJurisdiction(next);
    setLoading(true);
    try {
      await reload({ jurisdiction: next, page: 1 });
    } catch {
      toast.error("News could not reload.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTickerView() {
    const selected = ticker.trim().toUpperCase();
    if (!selected) return;
    setLoading(true);
    try {
      await reload({ ticker: selected, market, page: 1 });
    } catch {
      toast.error("Ticker news could not load.");
    } finally {
      setLoading(false);
    }
  }

  async function handlePoll() {
    setPolling(true);
    try {
      const run = await pollNews({ jurisdiction });
      toast.success(
        run.cache_hit
          ? "News is fresh. No provider calls used."
          : `News poll stored ${run.items_created} new item(s).`,
      );
      await reload({ jurisdiction, page: 1 });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "News poll failed.");
    } finally {
      setPolling(false);
    }
  }

  async function handleTickerRefresh() {
    const selected = ticker.trim().toUpperCase();
    if (!selected) return;
    setPolling(true);
    try {
      const run = await refreshTickerNews(selected, { market });
      toast.success(
        run.cache_hit
          ? `${selected} news is fresh. No provider calls used.`
          : `${selected} refresh stored ${run.items_created} new item(s).`,
      );
      await reload({ ticker: selected, market, page: 1 });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ticker refresh failed.");
    } finally {
      setPolling(false);
    }
  }

  async function handleCurrentPage(nextPage: number) {
    setLoading(true);
    try {
      await reload({ page: nextPage });
    } catch {
      toast.error("News page could not load.");
    } finally {
      setLoading(false);
    }
  }

  if (!overview) {
    return (
      <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-xl font-semibold">News Centre</h2>
        <p className="mt-2 text-sm text-zinc-500">
          {unavailable ? "Sign in again or refresh this page." : "No news has been stored yet."}
        </p>
      </section>
    );
  }

  const latestRun = overview.latest_run;
  const latestPoll = lastNewsPoll ?? null;
  const currentPage = overview.current_page;

  return (
    <div className="mx-auto max-w-[1500px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              News
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">News Centre</h2>
            <p className="mt-2 text-sm text-zinc-500">
              {latestRun
                ? `Last poll ${formatDate(latestRun.finished_at ?? latestRun.started_at)} · ${latestRun.target_key ?? "news"} · ${latestRun.cache_hit ? "fresh cache" : `${latestRun.items_created} new`} · ${latestRun.provider_calls} call(s)`
                : "Awaiting first news poll."}
            </p>
            {latestPoll ? (
              <p className="mt-1 text-xs text-zinc-500">
                Live update: {latestPoll.target_key ?? "news"} ·{" "}
                {latestPoll.cache_hit
                  ? "fresh cache"
                  : `${latestPoll.items_created} new item(s)`}
              </p>
            ) : null}
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
              onClick={() => void handlePoll()}
              disabled={polling}
              className={buttonPrimaryClassName}
            >
              {polling ? "Polling..." : `Poll ${marketLabel(jurisdiction)} news`}
            </button>
          </div>
        </div>

        <div className="grid gap-3 px-5 py-4 lg:grid-cols-[minmax(320px,1fr)_auto_auto] lg:items-end">
          <TickerSelector
            market={market}
            onMarketChange={setMarket}
            value={ticker}
            onTickerChange={setTicker}
            fetchDetailsOnSelect={false}
            tickerLabel="Ticker news"
            placeholder="AAPL or GTCO"
          />
          <button
            type="button"
            onClick={() => void handleTickerView()}
            disabled={loading || !ticker.trim()}
            className={buttonSecondaryClassName}
          >
            View ticker
          </button>
          <button
            type="button"
            onClick={() => void handleTickerRefresh()}
            disabled={polling || !ticker.trim()}
            className={buttonPrimaryClassName}
          >
            Refresh ticker
          </button>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <NewsPanel
          title="Current Feed"
          subtitle={paginationLabel(currentPage)}
          items={overview.current}
          footer={
            <NewsPaginationControls
              page={currentPage}
              loading={loading}
              onPageChange={handleCurrentPage}
            />
          }
        />
        <div className="space-y-5">
          <NewsPanel
            title={overview.ticker ? `${overview.ticker} Feed` : "Ticker Feed"}
            subtitle={`${overview.ticker_items.length} item${overview.ticker_items.length === 1 ? "" : "s"}`}
            items={overview.ticker_items}
            compact
          />
          <NewsPanel
            title="Watchlist Feed"
            subtitle={`${overview.watchlist_items.length} item${overview.watchlist_items.length === 1 ? "" : "s"}`}
            items={overview.watchlist_items}
            compact
          />
        </div>
      </section>
    </div>
  );
}

function NewsPanel({
  title,
  subtitle,
  items,
  compact,
  footer,
}: {
  title: string;
  subtitle: string;
  items: NewsItem[];
  compact?: boolean;
  footer?: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-zinc-500">{subtitle}</p>
      </div>
      {items.length === 0 ? (
        <p className="p-6 text-sm text-zinc-500">No items yet.</p>
      ) : (
        <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {items.map((item) => (
            <NewsRow key={item.id} item={item} compact={compact} />
          ))}
        </div>
      )}
      {footer}
    </section>
  );
}

function NewsPaginationControls({
  page,
  loading,
  onPageChange,
}: {
  page: NewsPagination;
  loading: boolean;
  onPageChange: (page: number) => void | Promise<void>;
}) {
  if (page.total <= page.page_size) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 px-5 py-3 text-xs dark:border-zinc-800">
      <span className="text-zinc-500">{paginationLabel(page)}</span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void onPageChange(page.page - 1)}
          disabled={loading || !page.has_previous}
          className={buttonSecondaryClassName}
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => void onPageChange(page.page + 1)}
          disabled={loading || !page.has_next}
          className={buttonSecondaryClassName}
        >
          Next
        </button>
      </div>
    </div>
  );
}

function NewsRow({ item, compact }: { item: NewsItem; compact?: boolean }) {
  const title = item.url ? (
    <a href={item.url} target="_blank" rel="noreferrer" className="hover:underline">
      {item.title}
    </a>
  ) : (
    item.title
  );
  return (
    <article className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
        <span>{item.source_name || providerLabel(item.provider)}</span>
        <span>·</span>
        <span>{formatDate(item.published_at ?? item.crawled_at)}</span>
        {item.event_type ? (
          <>
            <span>·</span>
            <span>{item.event_type.replaceAll("_", " ")}</span>
          </>
        ) : null}
        {item.sentiment_label ? (
          <>
            <span>·</span>
            <span className={sentimentClass(item.sentiment_label)}>
              {item.sentiment_label}
            </span>
          </>
        ) : null}
      </div>
      <h4 className={`${compact ? "mt-1 text-sm" : "mt-2 text-base"} font-semibold`}>
        {title}
      </h4>
      {!compact && item.summary ? (
        <p className="mt-2 line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          {item.summary}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.tickers.slice(0, compact ? 5 : 8).map((ticker) => (
          <Link
            key={ticker}
            href={`/news?ticker=${encodeURIComponent(ticker)}`}
            className="rounded-md border border-zinc-200 px-2 py-1 text-[11px] font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            {ticker}
          </Link>
        ))}
        {item.jurisdiction ? (
          <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11px] font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
            {item.jurisdiction}
          </span>
        ) : null}
        <span className="rounded-md bg-zinc-100 px-2 py-1 text-[11px] font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
          {providerLabel(item.provider)}
        </span>
      </div>
    </article>
  );
}

function formatDate(value: string | null | undefined) {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown time";
  return dateTimeFormat.format(date);
}

function marketLabel(value: "all" | "US" | "NG") {
  if (value === "US") return "US";
  if (value === "NG") return "NG";
  return "all-market";
}

function paginationLabel(page: NewsPagination) {
  if (page.total === 0) return "0 items";
  const start = (page.page - 1) * page.page_size + 1;
  const end = Math.min(page.page * page.page_size, page.total);
  return `${start}-${end} of ${page.total}`;
}

function providerLabel(provider: string) {
  if (provider === "ngnmarket") return "NGN Market";
  if (provider === "fmp") return "FMP";
  if (provider === "tiingo") return "Tiingo";
  if (provider === "polygon") return "Polygon";
  return provider;
}

function sentimentClass(sentiment: string) {
  const normalized = sentiment.toLowerCase();
  if (normalized.includes("positive") || normalized.includes("bullish")) {
    return "text-emerald-700 dark:text-emerald-400";
  }
  if (normalized.includes("negative") || normalized.includes("bearish")) {
    return "text-rose-700 dark:text-rose-400";
  }
  return "text-zinc-500";
}
