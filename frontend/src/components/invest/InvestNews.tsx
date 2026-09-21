"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Modal } from "@/components/ui/Modal";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputControlClassName,
} from "@/components/ui/form-styles";
import {
  getInvestNews,
  setNewsStar,
  type InvestNewsItem,
  type InvestNewsOverview,
  type InvestNewsPagination,
} from "@/lib/api";

type InvestNewsProps = {
  initialOverview: InvestNewsOverview | null;
  initialJurisdiction: "all" | "US" | "NG";
  unavailable: boolean;
};

const dateTimeFormat = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

const HEADLINES_PAGE_SIZE = 20;
const TICKER_PAGE_SIZE = 8;
const SYNC_MS = 60_000;

export function InvestNews({
  initialOverview,
  initialJurisdiction,
  unavailable,
}: InvestNewsProps) {
  const [overview, setOverview] = useState(initialOverview);
  const [jurisdiction, setJurisdiction] =
    useState<"all" | "US" | "NG">(initialJurisdiction);
  const [tickerQuery, setTickerQuery] = useState(initialOverview?.ticker ?? "");
  const [loading, setLoading] = useState(false);
  const [selectedArticle, setSelectedArticle] = useState<InvestNewsItem | null>(
    null,
  );
  const [savingStars, setSavingStars] = useState<Set<string>>(new Set());
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const reload = useCallback(
    async (next?: {
      ticker?: string | null;
      jurisdiction?: "all" | "US" | "NG";
      page?: number;
      tickerPage?: number;
    }) => {
      const nextTicker =
        next && "ticker" in next
          ? (next.ticker ?? "")
          : (overview?.ticker ?? "");
      const nextJurisdiction = next?.jurisdiction ?? jurisdiction;
      const nextPage = next?.page ?? overview?.headlines_page.page ?? 1;
      const nextTickerPage =
        next?.tickerPage ?? overview?.ticker_page?.page ?? 1;
      const data = await getInvestNews({
        ticker: nextTicker || undefined,
        market: nextTicker
          ? nextTicker.endsWith(".NG")
            ? "NG"
            : "US"
          : undefined,
        jurisdiction: nextJurisdiction,
        page: nextPage,
        page_size: HEADLINES_PAGE_SIZE,
        ticker_page: nextTicker ? nextTickerPage : undefined,
        ticker_page_size: nextTicker ? TICKER_PAGE_SIZE : undefined,
      });
      setOverview(data);
    },
    [
      jurisdiction,
      overview?.headlines_page.page,
      overview?.ticker,
      overview?.ticker_page?.page,
    ],
  );

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== "visible" || loading) return;
      void reload().catch(() => undefined);
    }, SYNC_MS);
    return () => window.clearInterval(timer);
  }, [loading, reload]);

  function replaceQuery(updates: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(updates)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    const query = params.toString();
    router.replace(query ? `${pathname}?${query}` : pathname, { scroll: false });
  }

  async function handleFilter(next: "all" | "US" | "NG") {
    setJurisdiction(next);
    replaceQuery({
      jurisdiction: next === "all" ? null : next,
      page: null,
    });
    setLoading(true);
    try {
      await reload({ jurisdiction: next, page: 1 });
    } catch {
      toast.error("Headlines could not reload.");
    } finally {
      setLoading(false);
    }
  }

  async function handleTickerFocus() {
    const selected = tickerQuery.trim().toUpperCase();
    if (!selected) return;
    replaceQuery({
      ticker: selected,
      market: selected.endsWith(".NG") ? "NG" : "US",
    });
    setLoading(true);
    try {
      await reload({ ticker: selected, tickerPage: 1 });
    } catch {
      toast.error("Could not load headlines for that ticker.");
    } finally {
      setLoading(false);
    }
  }

  async function handleClearTicker() {
    setTickerQuery("");
    replaceQuery({ ticker: null, market: null });
    setLoading(true);
    try {
      await reload({ ticker: "", tickerPage: 1 });
    } catch {
      toast.error("Could not clear ticker focus.");
    } finally {
      setLoading(false);
    }
  }

  async function handleHeadlinesPage(nextPage: number) {
    replaceQuery({ page: String(nextPage) });
    setLoading(true);
    try {
      await reload({ page: nextPage });
    } catch {
      toast.error("Could not load more headlines.");
    } finally {
      setLoading(false);
    }
  }

  async function handleToggleStar(item: InvestNewsItem) {
    const nextStarred = !item.starred;
    setOverview((current) =>
      current ? updateStar(current, item.id, nextStarred) : current,
    );
    setSelectedArticle((current) =>
      current?.id === item.id ? { ...current, starred: nextStarred } : current,
    );
    setSavingStars((current) => new Set(current).add(item.id));
    try {
      await setNewsStar(item.id, nextStarred);
      toast.success(nextStarred ? "Saved." : "Removed from saved.");
    } catch (error) {
      setOverview((current) =>
        current ? updateStar(current, item.id, item.starred) : current,
      );
      setSelectedArticle((current) =>
        current?.id === item.id ? { ...current, starred: item.starred } : current,
      );
      toast.error(error instanceof Error ? error.message : "Could not save.");
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
      <div className="mx-auto max-w-5xl rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {unavailable
          ? "Headlines could not load. Sign in again or refresh."
          : "No headlines yet."}
      </div>
    );
  }

  const personalEmpty =
    overview.portfolio_tickers.length === 0 &&
    overview.watchlist_tickers.length === 0;
  const incomeTickers = overview.income_tickers ?? [];
  const incomeItems = overview.income_items ?? [];
  const shelfTickers = incomeTickers.filter(isIncomeShelfSymbol);
  const ratesTickers = incomeTickers.filter(
    (symbol) => !isIncomeShelfSymbol(symbol),
  );

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">News</p>
        <h2 className="mt-1 text-2xl font-semibold">Rates and income</h2>
        <p className="mt-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          {overview.summary}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {ratesTickers.map((symbol) => (
            <ContextChip
              key={`r-${symbol}`}
              href={instrumentHref(symbol)}
              label={symbol}
              kind="Rates"
            />
          ))}
          {shelfTickers.map((symbol) => (
            <ContextChip
              key={`s-${symbol}`}
              href={instrumentHref(symbol)}
              label={symbol}
              kind="Shelf"
            />
          ))}
          {overview.portfolio_tickers.slice(0, 8).map((symbol) => (
            <ContextChip
              key={`p-${symbol}`}
              href={instrumentHref(symbol)}
              label={symbol}
              kind="Holding"
            />
          ))}
          {overview.watchlist_tickers.slice(0, 8).map((symbol) => (
            <ContextChip
              key={`w-${symbol}`}
              href={instrumentHref(symbol)}
              label={symbol}
              kind="Watch"
            />
          ))}
        </div>
        <div className="mt-5 flex flex-wrap items-end gap-3">
          <div className="min-w-[160px]">
            <label className="text-xs font-medium text-zinc-500" htmlFor="invest-news-market">
              Market
            </label>
            <select
              id="invest-news-market"
              value={jurisdiction}
              onChange={(event) =>
                void handleFilter(event.target.value as "all" | "US" | "NG")
              }
              disabled={loading}
              className={`mt-1.5 ${inputControlClassName}`}
            >
              <option value="all">All markets</option>
              <option value="US">United States</option>
              <option value="NG">Nigeria</option>
            </select>
          </div>
          <div className="min-w-[200px] flex-1">
            <label className="text-xs font-medium text-zinc-500" htmlFor="invest-news-ticker">
              Focus a ticker
            </label>
            <input
              id="invest-news-ticker"
              value={tickerQuery}
              onChange={(event) => setTickerQuery(event.target.value.toUpperCase())}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void handleTickerFocus();
                }
              }}
              placeholder="BIL, SHY, US-TBILL-13W…"
              className={`mt-1.5 ${inputControlClassName}`}
            />
          </div>
          <button
            type="button"
            onClick={() => void handleTickerFocus()}
            disabled={loading || !tickerQuery.trim()}
            className={buttonPrimaryClassName}
          >
            Show
          </button>
          {overview.ticker ? (
            <button
              type="button"
              onClick={() => void handleClearTicker()}
              disabled={loading}
              className={buttonSecondaryClassName}
            >
              Clear
            </button>
          ) : null}
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          T-bills, Treasuries, FGN context, and listed duration proxies lead.
          Discover stays unusual-price tape. This page is article headlines only.
        </p>
      </section>

      <NewsSection
        title="Rates and income"
        description="Treasury, bill, FGN, and listed duration-proxy headlines from Tiingo."
        items={incomeItems}
        emptyLabel="No rates or income headlines stored yet. Tiingo is queried for BIL, SHY, IEF, and TLT when this tape is thin."
        savingStars={savingStars}
        onOpen={setSelectedArticle}
        onToggleStar={handleToggleStar}
      />

      {overview.ticker ? (
        <NewsSection
          title={`${overview.ticker}`}
          description="Focused headlines for the ticker you selected."
          items={overview.ticker_items}
          emptyLabel={`No stored headlines for ${overview.ticker} yet.`}
          savingStars={savingStars}
          onOpen={setSelectedArticle}
          onToggleStar={handleToggleStar}
          footer={
            overview.ticker_page ? (
              <Pagination
                page={overview.ticker_page}
                loading={loading}
                onPageChange={(next) =>
                  void reload({ tickerPage: next }).catch(() =>
                    toast.error("Could not load more."),
                  )
                }
              />
            ) : null
          }
        />
      ) : null}

      <NewsSection
        title="For you"
        description={
          personalEmpty
            ? "Add names on Watchlist or take paper positions to fill this section."
            : "Stories linked to your holdings and watchlist, including T-bill and Treasury proxies."
        }
        items={overview.for_you}
        emptyLabel={
          personalEmpty
            ? "Nothing personal yet — start from Watchlist or Markets."
            : "No matching headlines for your names right now."
        }
        savingStars={savingStars}
        onOpen={setSelectedArticle}
        onToggleStar={handleToggleStar}
        actions={
          personalEmpty ? (
            <div className="flex flex-wrap gap-2">
              <Link href="/invest/watchlist" className={buttonSecondaryClassName}>
                Open watchlist
              </Link>
              <Link href="/invest/markets" className={buttonSecondaryClassName}>
                Browse markets
              </Link>
            </div>
          ) : null
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <NewsSection
          title="Holdings"
          description="News tied to what you own."
          items={overview.portfolio_items}
          emptyLabel="No holdings headlines yet."
          compact
          savingStars={savingStars}
          onOpen={setSelectedArticle}
          onToggleStar={handleToggleStar}
        />
        <NewsSection
          title="Watchlist"
          description="News for names you are tracking."
          items={overview.watchlist_items}
          emptyLabel="No watchlist headlines yet."
          compact
          savingStars={savingStars}
          onOpen={setSelectedArticle}
          onToggleStar={handleToggleStar}
        />
      </div>

      <NewsSection
        title="Listed equity tape"
        description="Index and sector headlines from the markets board. Rates proxies sit in the section above."
        items={overview.markets_items}
        emptyLabel="No listed-equity board headlines stored yet."
        savingStars={savingStars}
        onOpen={setSelectedArticle}
        onToggleStar={handleToggleStar}
      />

      <NewsSection
        title="All headlines"
        description={`Broader tape after rates. ${paginationLabel(overview.headlines_page)}`}
        items={overview.headlines}
        emptyLabel="No market headlines in this filter."
        savingStars={savingStars}
        onOpen={setSelectedArticle}
        onToggleStar={handleToggleStar}
        footer={
          <Pagination
            page={overview.headlines_page}
            loading={loading}
            onPageChange={(next) => void handleHeadlinesPage(next)}
          />
        }
      />

      {overview.saved_items.length > 0 ? (
        <NewsSection
          title="Saved"
          description={`${overview.saved_items.length} saved`}
          items={overview.saved_items}
          emptyLabel="Nothing saved."
          compact
          savingStars={savingStars}
          onOpen={setSelectedArticle}
          onToggleStar={handleToggleStar}
        />
      ) : null}

      <ArticleModal
        item={selectedArticle}
        onClose={() => setSelectedArticle(null)}
        onToggleStar={handleToggleStar}
        saving={selectedArticle ? savingStars.has(selectedArticle.id) : false}
      />
    </div>
  );
}

function ContextChip({
  href,
  label,
  kind,
}: {
  href: string;
  label: string;
  kind: string;
}) {
  return (
    <Link
      href={href}
      className="inline-flex items-center gap-1.5 rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
    >
      <span className="text-[10px] uppercase tracking-wide text-zinc-400">
        {kind}
      </span>
      {label}
    </Link>
  );
}

function NewsSection({
  title,
  description,
  items,
  emptyLabel,
  compact,
  savingStars,
  onOpen,
  onToggleStar,
  footer,
  actions,
}: {
  title: string;
  description: string;
  items: InvestNewsItem[];
  emptyLabel: string;
  compact?: boolean;
  savingStars: Set<string>;
  onOpen: (item: InvestNewsItem) => void;
  onToggleStar: (item: InvestNewsItem) => void;
  footer?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-zinc-500">{description}</p>
          </div>
          {actions}
        </div>
      </div>
      {items.length === 0 ? (
        <p className="p-5 text-sm text-zinc-500">{emptyLabel}</p>
      ) : (
        <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {items.map((item) => (
            <NewsRow
              key={item.id}
              item={item}
              compact={compact}
              saving={savingStars.has(item.id)}
              onOpen={onOpen}
              onToggleStar={onToggleStar}
            />
          ))}
        </div>
      )}
      {footer}
    </section>
  );
}

function NewsRow({
  item,
  compact,
  saving,
  onOpen,
  onToggleStar,
}: {
  item: InvestNewsItem;
  compact?: boolean;
  saving: boolean;
  onOpen: (item: InvestNewsItem) => void;
  onToggleStar: (item: InvestNewsItem) => void;
}) {
  return (
    <article className="px-5 py-4">
      <div className="flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-wide text-zinc-500">
        <span>{item.source_name || sourceLabel(item.provider)}</span>
        <span>·</span>
        <span>{formatDate(item.published_at ?? item.crawled_at)}</span>
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
          aria-label={item.starred ? "Unsave" : "Save"}
          className={`mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-lg border text-base transition ${
            item.starred
              ? "border-amber-300 bg-amber-50 text-amber-600 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
              : "border-zinc-200 text-zinc-400 hover:bg-zinc-50 dark:border-zinc-800 dark:hover:bg-zinc-900"
          }`}
        >
          {item.starred ? "★" : "☆"}
        </button>
        <button
          type="button"
          onClick={() => onOpen(item)}
          className={`text-left font-semibold hover:underline ${compact ? "text-sm" : "text-base"}`}
        >
          {item.title}
        </button>
      </div>
      {!compact && item.summary ? (
        <p className="mt-2 line-clamp-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
          {item.summary}
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {item.tickers.slice(0, compact ? 4 : 6).map((symbol) => (
          <Link
            key={symbol}
            href={instrumentHref(symbol)}
            className="rounded-md border border-zinc-200 px-2 py-1 text-[11px] font-medium text-zinc-600 hover:bg-zinc-50 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            {symbol}
          </Link>
        ))}
      </div>
    </article>
  );
}

function Pagination({
  page,
  loading,
  onPageChange,
}: {
  page: InvestNewsPagination;
  loading: boolean;
  onPageChange: (page: number) => void;
}) {
  if (page.total <= page.page_size) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 px-5 py-3 text-xs dark:border-zinc-800">
      <span className="text-zinc-500">{paginationLabel(page)}</span>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => onPageChange(page.page - 1)}
          disabled={loading || !page.has_previous}
          className={buttonSecondaryClassName}
        >
          Previous
        </button>
        <button
          type="button"
          onClick={() => onPageChange(page.page + 1)}
          disabled={loading || !page.has_next}
          className={buttonSecondaryClassName}
        >
          Next
        </button>
      </div>
    </div>
  );
}

function ArticleModal({
  item,
  onClose,
  onToggleStar,
  saving,
}: {
  item: InvestNewsItem | null;
  onClose: () => void;
  onToggleStar: (item: InvestNewsItem) => void;
  saving: boolean;
}) {
  const url = item?.url;
  return (
    <Modal
      open={Boolean(item)}
      onClose={onClose}
      title={item?.title ?? "Article"}
      description={
        item
          ? `${item.source_name || sourceLabel(item.provider)} · ${formatDate(
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
            title={item?.title ?? "Article"}
            className="h-full w-full flex-1 bg-white"
            referrerPolicy="no-referrer-when-downgrade"
            sandbox="allow-same-origin allow-scripts allow-popups allow-forms"
          />
        </div>
      ) : (
        <p className="text-sm text-zinc-500">This article has no source link.</p>
      )}
    </Modal>
  );
}

function updateStar(
  overview: InvestNewsOverview,
  itemId: string,
  starred: boolean,
): InvestNewsOverview {
  const updateItems = (items: InvestNewsItem[]) =>
    items.map((item) => (item.id === itemId ? { ...item, starred } : item));
  const sourceItem = [
    ...overview.income_items ?? [],
    ...overview.for_you,
    ...overview.portfolio_items,
    ...overview.watchlist_items,
    ...overview.markets_items,
    ...overview.headlines,
    ...overview.ticker_items,
    ...overview.saved_items,
  ].find((item) => item.id === itemId);
  const savedItems = starred
    ? sourceItem && !overview.saved_items.some((item) => item.id === itemId)
      ? [{ ...sourceItem, starred: true }, ...overview.saved_items]
      : updateItems(overview.saved_items)
    : overview.saved_items.filter((item) => item.id !== itemId);
  return {
    ...overview,
    income_items: updateItems(overview.income_items ?? []),
    for_you: updateItems(overview.for_you),
    portfolio_items: updateItems(overview.portfolio_items),
    watchlist_items: updateItems(overview.watchlist_items),
    markets_items: updateItems(overview.markets_items),
    headlines: updateItems(overview.headlines),
    ticker_items: updateItems(overview.ticker_items),
    saved_items: savedItems,
  };
}

function isIncomeShelfSymbol(symbol: string) {
  return /TBILL|TREASURY|FGN-/i.test(symbol);
}

function instrumentHref(symbol: string) {
  if (isIncomeShelfSymbol(symbol)) {
    return `/invest/fixed-income/${encodeURIComponent(symbol)}`;
  }
  return `/invest/instruments/${encodeURIComponent(symbol)}`;
}

function formatDate(value: string | null | undefined) {
  if (!value) return "unknown time";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "unknown time";
  return dateTimeFormat.format(date);
}

function paginationLabel(page: InvestNewsPagination) {
  if (page.total === 0) return "0 items";
  const start = (page.page - 1) * page.page_size + 1;
  const end = Math.min(page.page * page.page_size, page.total);
  return `${start}-${end} of ${page.total}`;
}

function sourceLabel(provider: string) {
  if (provider === "ngnmarket") return "NGN Market";
  if (provider === "tiingo") return "Tiingo";
  if (provider === "fmp") return "FMP";
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
