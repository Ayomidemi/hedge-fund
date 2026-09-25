"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import {
  addInvestWatchlistItem,
  createInvestOrder,
  getInvestInstrumentResearch,
  getInvestNews,
  type InvestInstrument,
  type InvestInstrumentResearch,
  type InvestNewsItem,
  type InvestPeaseView,
  type InvestResearchSection,
} from "@/lib/api";
import { money } from "@/components/invest/format";
import { InvestPriceChart } from "@/components/invest/InvestPriceChart";

type DetailTab = "overview" | "chart" | "news" | "financials" | "analysis" | "order";

export function InvestInstrumentDetail({
  instrument,
  research: initialResearch = null,
  initialTab = "overview",
}: {
  instrument: InvestInstrument;
  research?: InvestInstrumentResearch | null;
  initialTab?: DetailTab;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<DetailTab>(initialTab);
  const [amount, setAmount] = useState("500");
  const [side, setSide] = useState<"BUY" | "SELL">("BUY");
  const [reviewing, setReviewing] = useState(false);
  const [pending, setPending] = useState<"buy" | "watch" | null>(null);
  const [research, setResearch] = useState<InvestInstrumentResearch | null>(
    initialResearch,
  );
  const [researchLoading, setResearchLoading] = useState(!initialResearch);
  const [headlines, setHeadlines] = useState<InvestNewsItem[] | null>(null);

  useEffect(() => {
    if (initialResearch) {
      return;
    }
    let cancelled = false;
    setResearchLoading(true);
    void getInvestInstrumentResearch(instrument.ticker)
      .then((data) => {
        if (!cancelled) {
          setResearch(data);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setResearch(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setResearchLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [instrument.ticker, initialResearch]);

  useEffect(() => {
    if (tab !== "news" || headlines !== null) return;
    let cancelled = false;
    void getInvestNews({ ticker: instrument.ticker, ticker_page_size: 8 })
      .then((data) => {
        if (!cancelled) setHeadlines(data.ticker_items ?? []);
      })
      .catch(() => {
        if (!cancelled) setHeadlines([]);
      });
    return () => {
      cancelled = true;
    };
  }, [headlines, instrument.ticker, tab]);
  const price = instrument.price ? Number(instrument.price) : null;
  const estimatedUnits = useMemo(() => {
    const budget = Number(amount);
    if (!price || !Number.isFinite(budget) || budget <= 0) {
      return "--";
    }
    return (budget / price).toFixed(4);
  }, [amount, price]);

  async function handleOrder(event: FormEvent) {
    event.preventDefault();
    if (!reviewing) {
      setReviewing(true);
      return;
    }
    setPending("buy");
    try {
      const order = await createInvestOrder({
        ticker: instrument.ticker,
        side,
        amount,
      });
      toast.success(`${side} order filled for ${instrument.ticker} - ${order.status}`);
      router.push(`/invest/portfolio?placed=${order.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Order failed.");
    } finally {
      setPending(null);
    }
  }

  async function handleWatch() {
    setPending("watch");
    try {
      await addInvestWatchlistItem({ ticker: instrument.ticker });
      toast.success(`${instrument.ticker} added to your watchlist.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Watchlist update failed.");
    } finally {
      setPending(null);
    }
  }

  const sections = research?.sections ?? [];
  const overviewSections = sections.filter((section) =>
    ["instrument_profile", "price_context"].includes(section.id),
  );
  const financialSections = sections.filter((section) => section.id === "financials");
  const tapeSections = sections.filter((section) => section.id === "radar_context");
  const peaseView = research?.pease_view ?? null;

  return (
    <div className="w-full space-y-4">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-sm text-zinc-500">{instrument.name}</p>
            <h2 className="mt-1 text-3xl font-semibold">{instrument.ticker}</h2>
            <p className="mt-2 text-sm text-zinc-500">
              {instrument.sector ?? instrument.asset_class.replaceAll("_", " ")}
              {instrument.exchange ? ` - ${instrument.exchange}` : ""}
              {` - ${instrument.currency}`}
            </p>
          </div>
          <div className="text-left sm:text-right">
            <p className="text-xs uppercase tracking-wide text-zinc-500">Last price</p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">
              {instrument.price
                ? money(instrument.price, instrument.currency)
                : "Unavailable"}
            </p>
          </div>
        </div>

        {research ? (
          <p className="mt-5 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
            {research.overview}
          </p>
        ) : (
          <p className="mt-5 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
            {researchLoading
              ? "Loading research context…"
              : "Retail research context could not load, but the paper order ticket can still use the instrument record if a price is available."}
          </p>
        )}

        <div className="mt-5 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleWatch()}
            disabled={pending !== null}
            className={buttonSecondaryClassName}
          >
            {pending === "watch" ? "Saving..." : "Add to watchlist"}
          </button>
          <Link href="/invest/markets" className={buttonSecondaryClassName}>
            Search
          </Link>
        </div>
      </section>

      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-950">
        {([
          ["overview", "Overview"],
          ["chart", "Chart"],
          ["news", "News"],
          ["financials", "Financials"],
          ["analysis", "Analysis"],
          ["order", "Paper order"],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`shrink-0 rounded-xl px-4 py-2 text-sm font-medium ${
              tab === value
                ? "bg-emerald-800 text-white"
                : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {overviewSections.length > 0 ? (
            overviewSections.map((section) => (
              <ResearchSectionCard key={section.id} section={section} />
            ))
          ) : (
            <FallbackOverview instrument={instrument} />
          )}
        </div>
      ) : null}

      {tab === "chart" ? <InvestPriceChart ticker={instrument.ticker} /> : null}

      {tab === "news" ? (
        <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
          <h3 className="text-lg font-semibold">News</h3>
          {headlines === null ? (
            <p className="mt-3 text-sm text-zinc-500">Loading headlines…</p>
          ) : headlines.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500">
              No stored headlines for {instrument.ticker}.{" "}
              <Link href={research?.news_href ?? "/invest/news"} className="underline">
                Open News
              </Link>
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {headlines.map((item) => (
                <li key={item.id}>
                  <a
                    href={item.url ?? research?.news_href ?? "/invest/news"}
                    className="font-medium hover:underline"
                    target={item.url ? "_blank" : undefined}
                    rel={item.url ? "noreferrer" : undefined}
                  >
                    {item.title}
                  </a>
                  <p className="mt-1 text-xs text-zinc-500">
                    {item.source_name ?? item.provider}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : null}

      {tab === "financials" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          {financialSections.length > 0 ? (
            financialSections.map((section) => (
              <ResearchSectionCard key={section.id} section={section} />
            ))
          ) : (
            <section className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
              {researchLoading
                ? "Loading financials…"
                : "Financials are not available for this name yet."}
            </section>
          )}
        </div>
      ) : null}

      {tab === "analysis" ? (
        <div className="space-y-4">
          {peaseView ? <PeaseViewCard view={peaseView} /> : null}
          <div className="grid gap-4 lg:grid-cols-2">
            {tapeSections.length > 0 ? (
              tapeSections.map((section) => (
                <ResearchSectionCard key={section.id} section={section} />
              ))
            ) : peaseView ? null : (
              <section className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
                {researchLoading
                  ? "Loading analysis…"
                  : "Live factor scores have not been generated for this instrument yet."}
              </section>
            )}
          </div>
          {research?.withheld_capital_signals.length ? (
            <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
              <h3 className="text-lg font-semibold">Not shown on Invest</h3>
              <p className="mt-2 text-sm text-zinc-500">
                Fund-desk fields stay inside Pease Capital. This page is a factor
                snapshot, not a recommendation.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {research.withheld_capital_signals.map((item) => (
                  <span
                    key={item}
                    className="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
                  >
                    {item}
                  </span>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      ) : null}

      {tab === "order" ? (
        <form
          onSubmit={(event) => void handleOrder(event)}
          className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <h3 className="text-lg font-semibold">Listed-instrument paper order</h3>
          <p className="mt-2 text-sm text-zinc-500">
            This secondary flow is for exchange-listed instruments and ETF proxies.
            Fixed-income bills and bonds use the dedicated fixed-income detail page.
          </p>
          <div className="mt-4 grid grid-cols-2 gap-2">
            {(["BUY", "SELL"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setSide(value);
                  setReviewing(false);
                }}
                className={`rounded-xl border px-4 py-2 text-sm font-medium ${
                  side === value
                    ? "border-emerald-800 bg-emerald-800 text-white"
                    : "border-zinc-200 bg-white text-zinc-700 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300"
                }`}
              >
                {value === "BUY" ? "Buy" : "Sell"}
              </button>
            ))}
          </div>
          <label className="mt-4 block text-sm">
            <span className="text-xs uppercase tracking-wide text-zinc-500">
              Amount ({instrument.currency})
            </span>
            <input
              value={amount}
              onChange={(event) => {
                setAmount(event.target.value);
                setReviewing(false);
              }}
              className={inputClassName}
              inputMode="decimal"
            />
          </label>
          <p className="mt-2 text-sm text-zinc-500">Estimated units: {estimatedUnits}</p>
          {reviewing ? (
            <div className="mt-4 rounded-xl bg-zinc-50 p-4 text-sm dark:bg-zinc-900">
              <p className="font-medium">Review paper order</p>
              <p className="mt-1 text-zinc-500">
                {side} about {estimatedUnits} units of {instrument.ticker} for{" "}
                {money(amount, instrument.currency)}.
              </p>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              type="submit"
              disabled={pending !== null || !price}
              className={buttonPrimaryClassName}
            >
              {pending === "buy"
                ? "Submitting..."
                : reviewing
                  ? "Confirm paper order"
                  : "Review order"}
            </button>
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void handleWatch()}
              className={buttonSecondaryClassName}
            >
              {pending === "watch" ? "Saving..." : "Add to watchlist"}
            </button>
            <Link href="/invest/markets" className={buttonSecondaryClassName}>
              Back to markets
            </Link>
          </div>
        </form>
      ) : null}
    </div>
  );
}

function PeaseViewCard({ view }: { view: InvestPeaseView }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-wide text-zinc-500">Pease View</p>
          <h3 className="mt-1 text-lg font-semibold">{view.stance_label}</h3>
          <p className="mt-2 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
            {view.summary}
          </p>
        </div>
        <span className={`rounded-md px-2 py-1 text-xs font-medium ${stanceClass(view.stance)}`}>
          {Number(view.coverage_pct).toFixed(0)}% coverage
        </span>
      </div>
      <div className="mt-5 space-y-3">
        {view.factors.map((factor) => {
          const score = factor.score == null ? null : Number(factor.score);
          return (
            <div key={factor.id}>
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{factor.label}</span>
                <span className={toneClass(factor.tone)}>
                  {score == null ? "Unavailable" : `${Math.round(score)}/100`}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-900">
                <div
                  className={`h-full rounded-full ${barClass(factor.tone)}`}
                  style={{ width: `${score == null ? 0 : Math.max(4, Math.min(100, score))}%` }}
                />
              </div>
              <p className="mt-1 text-xs text-zinc-500">{factor.notes}</p>
            </div>
          );
        })}
      </div>
      {view.looks_good.length > 0 ? (
        <div className="mt-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            What looks good
          </p>
          <ul className="mt-2 space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
            {view.looks_good.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {view.watch_outs.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            What to watch
          </p>
          <ul className="mt-2 space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
            {view.watch_outs.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {view.radar_note ? (
        <p className="mt-4 text-sm text-zinc-600 dark:text-zinc-400">{view.radar_note}</p>
      ) : null}
      {view.warnings.length > 0 ? (
        <div className="mt-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Data gaps
          </p>
          <ul className="mt-2 space-y-1 text-xs text-zinc-500">
            {view.warnings.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function ResearchSectionCard({ section }: { section: InvestResearchSection }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="text-lg font-semibold">{section.title}</h3>
      <p className="mt-2 text-sm text-zinc-500">{section.summary}</p>
      {section.metrics.length > 0 ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {section.metrics.map((metric) => (
            <div
              key={`${section.id}-${metric.label}`}
              className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-900"
            >
              <p className="text-xs uppercase tracking-wide text-zinc-500">
                {metric.label}
              </p>
              <p className={`mt-1 font-semibold ${toneClass(metric.tone)}`}>
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      ) : null}
      {section.notes.length > 0 ? (
        <ul className="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          {section.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}

function FallbackOverview({ instrument }: { instrument: InvestInstrument }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <h3 className="text-lg font-semibold">Instrument profile</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <ProfileDetail label="Asset class" value={instrument.asset_class} />
        <ProfileDetail label="Exchange" value={instrument.exchange ?? "Unavailable"} />
        <ProfileDetail label="Currency" value={instrument.currency} />
        <ProfileDetail label="Sector" value={instrument.sector ?? "Not classified"} />
      </div>
    </section>
  );
}

function ProfileDetail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold capitalize">{value.replaceAll("_", " ")}</p>
    </div>
  );
}

function barClass(tone: string) {
  if (tone === "positive") return "bg-emerald-700";
  if (tone === "negative") return "bg-red-700";
  return "bg-zinc-400";
}

function stanceClass(stance: string) {
  if (stance === "constructive") {
    return "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (stance === "caution") {
    return "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200";
  }
  if (stance === "incomplete") {
    return "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
  }
  return "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300";
}

function toneClass(tone: string) {
  if (tone === "positive") {
    return "text-emerald-700 dark:text-emerald-200";
  }
  if (tone === "negative") {
    return "text-red-700 dark:text-red-200";
  }
  if (tone === "income") {
    return "text-amber-800 dark:text-amber-200";
  }
  return "text-zinc-900 dark:text-zinc-100";
}
