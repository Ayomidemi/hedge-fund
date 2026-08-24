"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useLiveData } from "@/components/providers/LiveDataProvider";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import { Modal } from "@/components/ui/Modal";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputControlClassName,
} from "@/components/ui/form-styles";
import {
  getNewsOverview,
  refreshTickerNews,
  setNewsStar,
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
const TICKER_PAGE_SIZE = 8;
const NEWS_OVERVIEW_SYNC_INTERVAL_MS = 60_000;

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
  const [selectedArticle, setSelectedArticle] = useState<NewsItem | null>(null);
  const [savingStars, setSavingStars] = useState<Set<string>>(new Set());
  const { lastNewsPoll } = useLiveData();
  const handledPollRunId = useRef<string | null>(null);
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (overview === null && initialOverview) {
      setOverview(initialOverview);
    }
  }, [initialOverview, overview]);

  const reload = useCallback(async (next?: {
    ticker?: string | null;
    market?: TickerMarket;
    jurisdiction?: "all" | "US" | "NG";
    page?: number;
    tickerPage?: number;
  }) => {
    const nextTicker =
      next && "ticker" in next ? (next.ticker ?? "") : (overview?.ticker ?? "");
    const nextMarket = next?.market ?? market;
    const nextJurisdiction = next?.jurisdiction ?? jurisdiction;
    const nextPage = next?.page ?? overview?.current_page.page ?? 1;
    const nextTickerPage =
      next?.tickerPage ?? overview?.ticker_page?.page ?? 1;
    const data = await getNewsOverview({
      ticker: nextTicker || undefined,
      market: nextTicker ? nextMarket : undefined,
      jurisdiction: nextJurisdiction,
      page: nextPage,
      page_size: CURRENT_PAGE_SIZE,
      ticker_page: nextTicker ? nextTickerPage : undefined,
      ticker_page_size: nextTicker ? TICKER_PAGE_SIZE : undefined,
    });
    setOverview(data);
  }, [
    jurisdiction,
    market,
    overview?.current_page.page,
    overview?.ticker,
    overview?.ticker_page?.page,
  ]);

  useEffect(() => {
    if (!lastNewsPoll || handledPollRunId.current === lastNewsPoll.run_id) return;
    handledPollRunId.current = lastNewsPoll.run_id;
    void reload(
      lastNewsPoll.target_scope === "ticker" ? { tickerPage: 1 } : { page: 1 },
    ).catch(() => {
      toast.error("Live news update could not load.");
    });
  }, [lastNewsPoll, reload]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || loading || polling) return;
      void reload().catch(() => {
        toast.error("News sync could not load.");
      });
    }, NEWS_OVERVIEW_SYNC_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [loading, polling, reload]);

  function replaceTickerQuery(nextTicker: string, nextMarket?: TickerMarket) {
    const params = new URLSearchParams(searchParams.toString());
    if (nextTicker) {
      params.set("ticker", nextTicker);
      if (nextMarket) params.set("market", nextMarket);
    } else {
      params.delete("ticker");
      params.delete("market");
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
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

  async function handleTickerNews() {
    const selected = ticker.trim().toUpperCase();
    if (!selected) return;
    setPolling(true);
    try {
      const run = await refreshTickerNews(selected, { market });
      handledPollRunId.current = run.id;
      toast.success(
        run.cache_hit
          ? `${selected} news is fresh. No provider calls used.`
          : `${selected} refresh stored ${run.items_created} new item(s).`,
      );
      replaceTickerQuery(selected, market);
      await reload({ ticker: selected, market, tickerPage: 1 });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Ticker refresh failed.");
    } finally {
      setPolling(false);
    }
  }

  async function handleClearTicker() {
    setTicker("");
    replaceTickerQuery("");
    setLoading(true);
    try {
      await reload({ ticker: "", tickerPage: 1 });
    } catch {
      toast.error("Ticker news could not clear.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTickerSelect(nextTicker: string) {
    const selected = nextTicker.trim().toUpperCase();
    if (!selected) return;
    const nextMarket: TickerMarket = selected.endsWith(".NG") ? "NG" : market;
    setTicker(selected);
    setMarket(nextMarket);
    replaceTickerQuery(selected, nextMarket);
    setPolling(true);
    try {
      await reload({ ticker: selected, market: nextMarket, tickerPage: 1 });
    } catch {
      toast.error("Ticker news could not load.");
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

  async function handleTickerPage(nextPage: number) {
    setLoading(true);
    try {
      await reload({ tickerPage: nextPage });
    } catch {
      toast.error("Ticker news page could not load.");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleStar(item: NewsItem) {
    const nextStarred = !item.starred;
    setOverview((current) =>
      current ? updateNewsItemStar(current, item.id, nextStarred) : current,
    );
    setSelectedArticle((current) =>
      current?.id === item.id ? { ...current, starred: nextStarred } : current,
    );
    setSavingStars((current) => new Set(current).add(item.id));
    try {
      await setNewsStar(item.id, nextStarred);
      toast.success(nextStarred ? "News saved." : "News unsaved.");
    } catch (error) {
      setOverview((current) =>
        current ? updateNewsItemStar(current, item.id, item.starred) : current,
      );
      setSelectedArticle((current) =>
        current?.id === item.id ? { ...current, starred: item.starred } : current,
      );
      toast.error(error instanceof Error ? error.message : "News save failed.");
    } finally {
      setSavingStars((current) => {
        const next = new Set(current);
        next.delete(item.id);
        return next;
      });
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
  const tickerPage = overview.ticker_page;

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
                ? `Last poll ${formatDate(latestRun.finished_at ?? latestRun.started_at)} · ${latestRun.target_key ?? "news"} · ${latestRun.cache_hit ? "fresh cache" : `${latestRun.items_created} new`}`
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
          <div className="w-full min-w-[220px] sm:w-64">
            <label className="block text-xs font-medium text-zinc-500" htmlFor="news-market-filter">
              Market feed
            </label>
            <select
              id="news-market-filter"
              value={jurisdiction}
              onChange={(event) =>
                void handleFilter(event.target.value as "all" | "US" | "NG")
              }
              disabled={loading || polling}
              className={`mt-1.5 ${inputControlClassName}`}
            >
              <option value="all">All markets</option>
              <option value="US">United States</option>
              <option value="NG">Nigeria</option>
            </select>
          </div>
        </div>

        <div className="grid gap-3 px-5 py-4 lg:grid-cols-[minmax(320px,1fr)_auto] lg:items-end">
          <TickerSelector
            market={market}
            onMarketChange={setMarket}
            value={ticker}
            onTickerChange={setTicker}
            fetchDetailsOnSelect={false}
            tickerLabel="Ticker news"
            placeholder="AAPL or GTCO"
            allowClear
            onClear={() => void handleClearTicker()}
          />
          <button
            type="button"
            onClick={() => void handleTickerNews()}
            disabled={loading || polling || !ticker.trim()}
            className={buttonPrimaryClassName}
          >
            {polling ? "Loading ticker news..." : "Show ticker news"}
          </button>
        </div>
      </section>

      <section className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <NewsPanel
          title="Current Feed"
          subtitle={paginationLabel(currentPage)}
          items={overview.current}
          onOpenArticle={setSelectedArticle}
          onToggleStar={handleToggleStar}
          onSelectTicker={(symbol) => void handleTickerSelect(symbol)}
          savingStars={savingStars}
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
            title="Saved News"
            subtitle={`${overview.saved_items.length} saved`}
            items={overview.saved_items}
            onOpenArticle={setSelectedArticle}
            onToggleStar={handleToggleStar}
            onSelectTicker={(symbol) => void handleTickerSelect(symbol)}
            savingStars={savingStars}
            compact
          />
          <NewsPanel
            title={overview.ticker ? `${overview.ticker} Feed` : "Ticker Feed"}
            subtitle={
              tickerPage
                ? paginationLabel(tickerPage)
                : "Search a ticker. The current tape stays on the left."
            }
            items={overview.ticker_items}
            emptyLabel={
              overview.ticker
                ? `No stored items for ${overview.ticker}.`
                : "Search a ticker to load its feed. US/NG current news keeps updating independently."
            }
            onOpenArticle={setSelectedArticle}
            onToggleStar={handleToggleStar}
            onSelectTicker={(symbol) => void handleTickerSelect(symbol)}
            savingStars={savingStars}
            compact
            footer={
              tickerPage ? (
                <NewsPaginationControls
                  page={tickerPage}
                  loading={loading || polling}
                  onPageChange={handleTickerPage}
                />
              ) : null
            }
          />
          <NewsPanel
            title="Watchlist Feed"
            subtitle={`${overview.watchlist_items.length} item${overview.watchlist_items.length === 1 ? "" : "s"}`}
            items={overview.watchlist_items}
            onOpenArticle={setSelectedArticle}
            onToggleStar={handleToggleStar}
            onSelectTicker={(symbol) => void handleTickerSelect(symbol)}
            savingStars={savingStars}
            compact
          />
        </div>
      </section>
      <NewsArticleModal
        item={selectedArticle}
        onClose={() => setSelectedArticle(null)}
        onToggleStar={handleToggleStar}
        saving={selectedArticle ? savingStars.has(selectedArticle.id) : false}
      />
    </div>
  );
}

function NewsPanel({
  title,
  subtitle,
  items,
  compact,
  emptyLabel = "No items yet.",
  footer,
  onOpenArticle,
  onToggleStar,
  onSelectTicker,
  savingStars,
}: {
  title: string;
  subtitle: string;
  items: NewsItem[];
  compact?: boolean;
  emptyLabel?: string;
  footer?: ReactNode;
  onOpenArticle: (item: NewsItem) => void;
  onToggleStar: (item: NewsItem) => void;
  onSelectTicker: (ticker: string) => void;
  savingStars: Set<string>;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="text-xs text-zinc-500">{subtitle}</p>
      </div>
      {items.length === 0 ? (
        <p className="p-6 text-sm text-zinc-500">{emptyLabel}</p>
      ) : (
        <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {items.map((item) => (
            <NewsRow
              key={item.id}
              item={item}
              compact={compact}
              onOpenArticle={onOpenArticle}
              onToggleStar={onToggleStar}
              onSelectTicker={onSelectTicker}
              saving={savingStars.has(item.id)}
            />
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

function NewsRow({
  item,
  compact,
  onOpenArticle,
  onToggleStar,
  onSelectTicker,
  saving,
}: {
  item: NewsItem;
  compact?: boolean;
  onOpenArticle: (item: NewsItem) => void;
  onToggleStar: (item: NewsItem) => void;
  onSelectTicker: (ticker: string) => void;
  saving: boolean;
}) {
  const title = item.url ? (
    <button
      type="button"
      onClick={() => onOpenArticle(item)}
      className="text-left hover:underline"
    >
      {item.title}
    </button>
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
      <div className="mt-2 flex items-start gap-3">
        <button
          type="button"
          onClick={() => onToggleStar(item)}
          disabled={saving}
          aria-label={item.starred ? "Unsave news" : "Save news"}
          title={item.starred ? "Unsave news" : "Save news"}
          className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border text-base transition ${
            item.starred
              ? "border-amber-300 bg-amber-50 text-amber-600 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
              : "border-zinc-200 text-zinc-400 hover:bg-zinc-50 hover:text-zinc-700 dark:border-zinc-800 dark:hover:bg-zinc-900 dark:hover:text-zinc-200"
          }`}
        >
          {item.starred ? "★" : "☆"}
        </button>
        <h4 className={`${compact ? "text-sm" : "text-base"} font-semibold`}>
          {title}
        </h4>
      </div>
      {!compact && item.summary ? (
        <p className="mt-2 line-clamp-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          {item.summary}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.tickers.slice(0, compact ? 5 : 8).map((symbol) => (
          <button
            key={symbol}
            type="button"
            onClick={() => onSelectTicker(symbol)}
            className="rounded-md border border-zinc-200 px-2 py-1 text-[11px] font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            {symbol}
          </button>
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

function NewsArticleModal({
  item,
  onClose,
  onToggleStar,
  saving,
}: {
  item: NewsItem | null;
  onClose: () => void;
  onToggleStar: (item: NewsItem) => void;
  saving: boolean;
}) {
  const url = item?.url;
  return (
    <Modal
      open={Boolean(item)}
      onClose={onClose}
      title={item?.title ?? "News article"}
      description={
        item
          ? `${item.source_name || providerLabel(item.provider)} · ${formatDate(
              item.published_at ?? item.crawled_at,
            )}`
          : undefined
      }
      size="screen"
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          {item ? (
            <button
              type="button"
              onClick={() => onToggleStar(item)}
              disabled={saving}
              className={buttonSecondaryClassName}
            >
              {item.starred ? "★ Saved" : "☆ Save"}
            </button>
          ) : null}
          {url ? (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              className={buttonPrimaryClassName}
            >
              Open original
            </a>
          ) : null}
        </div>
      }
    >
      {url ? (
        <div className="flex h-[72dvh] min-h-[520px] flex-col overflow-hidden rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <iframe
            src={url}
            title={item?.title ?? "News article"}
            className="h-full w-full flex-1 bg-white"
            referrerPolicy="no-referrer-when-downgrade"
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          />
        </div>
      ) : (
        <p className="text-sm text-zinc-500">This article has no source link.</p>
      )}
      {url ? (
        <p className="mt-3 text-xs text-zinc-500">
          Some publishers block embedded viewing. Use Open original when the article cannot be displayed here.
        </p>
      ) : null}
    </Modal>
  );
}

function updateNewsItemStar(
  overview: NewsOverview,
  itemId: string,
  starred: boolean,
): NewsOverview {
  const updateItems = (items: NewsItem[]) =>
    items.map((item) => (item.id === itemId ? { ...item, starred } : item));
  const sourceItem = [
    ...overview.current,
    ...overview.ticker_items,
    ...overview.watchlist_items,
    ...overview.saved_items,
  ].find((item) => item.id === itemId);
  const savedItems = starred
    ? sourceItem && !overview.saved_items.some((item) => item.id === itemId)
      ? [{ ...sourceItem, starred: true }, ...overview.saved_items]
      : updateItems(overview.saved_items)
    : overview.saved_items.filter((item) => item.id !== itemId);
  return {
    ...overview,
    current: updateItems(overview.current),
    ticker_items: updateItems(overview.ticker_items),
    watchlist_items: updateItems(overview.watchlist_items),
    saved_items: savedItems,
  };
}

function formatDate(value: string | null | undefined) {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown time";
  return dateTimeFormat.format(date);
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
