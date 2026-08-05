"use client";

import { FormEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/Modal";
import {
  createTickerAnalysis,
  getTickerMemo,
  getTickerPrefill,
  type TickerAnalysis,
  type TickerAnalysisInput,
  type TickerMemo,
  type TickerMemoSummary,
  type TickerPrefill,
} from "@/lib/api";

type TickerAnalystProps = {
  recentMemos: TickerMemoSummary[];
  isUnavailable: boolean;
};

const scoreFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

function score(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return scoreFormatter.format(Number(value));
}

function weight(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

export function TickerAnalyst({ recentMemos, isUnavailable }: TickerAnalystProps) {
  const [analysis, setAnalysis] = useState<TickerAnalysis | null>(null);
  const [error, setError] = useState<string | null>(isUnavailable ? "Backend unavailable." : null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPrefilling, setIsPrefilling] = useState(false);
  const [selectedMemo, setSelectedMemo] = useState<TickerMemo | null>(null);
  const [memoLoadingId, setMemoLoadingId] = useState<string | null>(null);
  const [prefillWarnings, setPrefillWarnings] = useState<string[]>([]);
  const formRef = useRef<HTMLFormElement>(null);
  const router = useRouter();

  async function handlePrefill() {
    const form = formRef.current;
    if (!form) {
      return;
    }

    const ticker = textValue(new FormData(form), "ticker");
    if (!ticker) {
      setError("Enter a ticker first.");
      return;
    }

    setIsPrefilling(true);
    setError(null);
    setPrefillWarnings([]);

    try {
      const result = await getTickerPrefill(ticker);
      fillFormFromPrefill(form, result);
      setPrefillWarnings(result.source_warnings);
    } catch {
      setError("Ticker prefill was not available.");
    } finally {
      setIsPrefilling(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setIsSubmitting(true);
    setError(null);

    try {
      const payload = buildPayload(formData);
      const result = await createTickerAnalysis(payload);
      setAnalysis(result);
      form.reset();
      router.refresh();
    } catch {
      setError("Ticker analysis was not saved.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleOpenMemo(memoId: string) {
    setMemoLoadingId(memoId);
    setError(null);

    try {
      const memo = await getTickerMemo(memoId);
      setSelectedMemo(memo);
    } catch {
      setError("Past analysis could not be loaded.");
    } finally {
      setMemoLoadingId(null);
    }
  }

  return (
    <div className="mx-auto grid max-w-[1560px] gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
      <section className="space-y-5">
        <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <div className="border-b border-zinc-200 px-4 py-4 dark:border-zinc-800">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Research Intake
            </p>
            <h2 className="mt-1 text-base font-semibold">Ticker Analyst</h2>
          </div>

          <form ref={formRef} onSubmit={handleSubmit} className="grid gap-5 p-4">
            <div className="grid gap-4 lg:grid-cols-3">
              <Field label="Ticker">
                <div className="mt-1 flex gap-2">
                  <input
                    name="ticker"
                    required
                    className={`${inputClassNameNoMargin} uppercase`}
                  />
                  <button
                    type="button"
                    onClick={handlePrefill}
                    disabled={isPrefilling || isSubmitting}
                    className={secondaryButtonClassName}
                  >
                    {isPrefilling ? "Fetching..." : "Fetch"}
                  </button>
                </div>
              </Field>
              <Field label="Name">
                <input name="name" required className={inputClassName} />
              </Field>
              <Field label="Asset Class">
                <select name="asset_class" className={inputClassName}>
                  <option value="equity">Equity</option>
                  <option value="etf">ETF</option>
                  <option value="bond">Bond</option>
                  <option value="commodity">Commodity</option>
                  <option value="cash_equivalent">Cash Equivalent</option>
                  <option value="other">Other</option>
                </select>
              </Field>
              <Field label="Exchange">
                <input name="exchange" defaultValue="NASDAQ" className={inputClassName} />
              </Field>
              <Field label="Sector">
                <input name="sector" className={inputClassName} />
              </Field>
              <Field label="Industry">
                <input name="industry" className={inputClassName} />
              </Field>
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricField label="Price" name="current_price" />
              <MetricField label="Market Cap $B" name="market_cap_billion" />
              <MetricField label="P/E" name="pe_ratio" />
              <MetricField label="Forward P/E" name="forward_pe" />
              <MetricField label="Revenue Growth %" name="revenue_growth_pct" />
              <MetricField label="Earnings Growth %" name="earnings_growth_pct" />
              <MetricField label="FCF Yield %" name="free_cash_flow_yield_pct" />
              <MetricField label="Net Margin %" name="net_margin_pct" />
              <MetricField label="Debt / Equity" name="debt_to_equity" />
              <MetricField label="Price vs 200D %" name="price_vs_200d_pct" />
              <MetricField label="6M Rel. Strength %" name="relative_strength_6m_pct" />
              <MetricField label="30D Volatility %" name="volatility_30d_pct" />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="Time Horizon">
                <input name="time_horizon" defaultValue="6-18 months" className={inputClassName} />
              </Field>
              <Field label="Source Reference">
                <input name="source_reference" className={inputClassName} />
              </Field>
            </div>

            {prefillWarnings.length > 0 && (
              <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {prefillWarnings.join(" ")}
              </div>
            )}

            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="Investment Question">
                <textarea name="investment_question" rows={3} className={inputClassName} />
              </Field>
              <Field label="Thesis">
                <textarea name="thesis" required rows={3} className={inputClassName} />
              </Field>
              <Field label="Bull Case">
                <textarea name="bull_case" rows={3} className={inputClassName} />
              </Field>
              <Field label="Base Case">
                <textarea name="base_case" rows={3} className={inputClassName} />
              </Field>
              <Field label="Bear Case">
                <textarea name="bear_case" rows={3} className={inputClassName} />
              </Field>
              <Field label="Thesis Breakers">
                <textarea name="thesis_breakers" rows={3} className={inputClassName} />
              </Field>
              <Field label="Risk Notes">
                <textarea name="risk_notes" rows={3} className={inputClassName} />
              </Field>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-900">
              <div className="min-h-5 text-sm text-zinc-500">
                {error ? <span className="text-red-600 dark:text-red-300">{error}</span> : null}
              </div>
              <button disabled={isSubmitting} className={buttonClassName}>
                {isSubmitting ? "Analyzing..." : "Save Analysis"}
              </button>
            </div>
          </form>
        </div>

        <AnalysisPanel analysis={analysis} />
      </section>

      <aside className="space-y-5">
        <MemoHistory
          memos={recentMemos}
          loadingId={memoLoadingId}
          onOpenMemo={handleOpenMemo}
        />
      </aside>

      <TickerMemoModal memo={selectedMemo} onClose={() => setSelectedMemo(null)} />
    </div>
  );
}

function AnalysisPanel({ analysis }: { analysis: TickerAnalysis | null }) {
  if (!analysis) {
    return (
      <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Latest Output
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-4">
          {["Composite", "Confidence", "Conviction", "Weight"].map((item) => (
            <div key={item} className="h-24 rounded-md border border-zinc-100 bg-zinc-50 dark:border-zinc-900 dark:bg-zinc-900" />
          ))}
        </div>
      </div>
    );
  }

  const metrics = [
    ["Composite", score(analysis.composite_score)],
    ["Confidence", score(analysis.confidence_score)],
    ["Conviction", score(analysis.conviction_score)],
    ["Weight", weight(analysis.recommended_weight)],
  ];

  return (
    <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Latest Output
          </p>
          <h2 className="mt-1 text-base font-semibold">
            {analysis.memo.instrument.ticker} / {formatLabel(analysis.action)}
          </h2>
        </div>
        <span className="rounded-md bg-zinc-950 px-2.5 py-1.5 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-950">
          {formatLabel(analysis.classification)}
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div key={label} className="border-l border-zinc-200 pl-4 dark:border-zinc-800">
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              {label}
            </p>
            <p className="mt-2 text-2xl font-semibold tracking-normal">{value}</p>
          </div>
        ))}
      </div>

      <div className="mt-5 grid gap-3 lg:grid-cols-5">
        {analysis.scorecard.map((item) => (
          <div key={item.name} className="rounded-md border border-zinc-100 p-3 dark:border-zinc-900">
            <div className="flex items-center justify-between gap-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                {item.name}
              </p>
              <span className="font-mono text-sm">{score(item.score)}</span>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {item.notes}
            </p>
          </div>
        ))}
      </div>

      <p className="mt-4 rounded-md bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
        {analysis.evidence_summary}
      </p>
    </div>
  );
}

function MemoHistory({
  loadingId,
  memos,
  onOpenMemo,
}: {
  loadingId: string | null;
  memos: TickerMemoSummary[];
  onOpenMemo: (memoId: string) => void;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-4 py-4 dark:border-zinc-800">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Recent Memos
        </p>
        <h2 className="mt-1 text-base font-semibold">Ticker Research</h2>
      </div>
      <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
        {memos.map((memo) => (
          <button
            key={memo.id}
            type="button"
            onClick={() => onOpenMemo(memo.id)}
            className="block w-full p-4 text-left transition hover:bg-zinc-50 dark:hover:bg-zinc-900"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-semibold">{memo.ticker}</p>
                <p className="truncate text-sm text-zinc-500">{memo.name}</p>
              </div>
              <span className="shrink-0 rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
                {loadingId === memo.id ? "..." : score(memo.composite_score)}
              </span>
            </div>
            <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {memo.executive_view}
            </p>
            <div className="mt-3 flex flex-wrap gap-2 text-xs text-zinc-500">
              <span>{memo.memo_date}</span>
              <span>{formatLabel(memo.classification)}</span>
              {memo.action ? <span>{formatLabel(memo.action)}</span> : null}
            </div>
          </button>
        ))}
        {memos.length === 0 && (
          <div className="px-4 py-8 text-center text-sm text-zinc-500">
            No memos yet
          </div>
        )}
      </div>
    </div>
  );
}

function TickerMemoModal({
  memo,
  onClose,
}: {
  memo: TickerMemo | null;
  onClose: () => void;
}) {
  const scoreData = parseMemoScores(memo);
  const modalTitle = memo ? `${memo.instrument.ticker} analysis` : "Ticker analysis";

  return (
    <Modal
      open={memo !== null}
      onClose={onClose}
      title={modalTitle}
      description={memo?.executive_view}
      size="xl"
    >
      {memo && (
        <div className="max-h-[70vh] overflow-y-auto pr-1">
          <div className="grid gap-3 sm:grid-cols-4">
            {[
              ["Action", formatLabel(scoreData.action ?? "watch")],
              ["Composite", score(scoreData.composite_score)],
              ["Confidence", score(scoreData.confidence_score)],
              ["Weight", scoreData.recommended_weight ? weight(scoreData.recommended_weight) : "-"],
            ].map(([label, value]) => (
              <div
                key={label}
                className="rounded-lg border border-zinc-100 bg-zinc-50 px-3.5 py-3 dark:border-zinc-900 dark:bg-zinc-900"
              >
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  {label}
                </p>
                <p className="mt-1.5 text-lg font-semibold text-zinc-950 dark:text-zinc-50">
                  {value}
                </p>
              </div>
            ))}
          </div>

          <section className="mt-5 grid gap-3 lg:grid-cols-3">
            <AnalysisLayer
              title="Descriptive"
              rows={[
                ["Valuation", metricText(scoreData, "Valuation")],
                ["Growth", metricText(scoreData, "Growth")],
                ["Margins / Quality", metricText(scoreData, "Quality")],
                ["Leverage / Risk", metricText(scoreData, "Balance Sheet Risk")],
                ["Volatility / Momentum", metricText(scoreData, "Momentum")],
              ]}
            />
            <AnalysisLayer
              title="Comparative"
              rows={[
                ["History", "Price vs 200D and 6M trend are current proxies."],
                ["Sector", "Sector-relative benchmark pending."],
                ["Peers", "Peer set and percentile rank pending."],
                ["Universe", "Cross-sectional rank pending."],
              ]}
            />
            <AnalysisLayer
              title="Predictive"
              rows={[
                ["Expected return", "Pending model training."],
                ["Downside distribution", "Pending downside model."],
                ["Model confidence", score(scoreData.confidence_score)],
                ["Portfolio improvement", "Pending portfolio-fit model."],
              ]}
            />
          </section>

          <section className="mt-5 grid gap-4 lg:grid-cols-2">
            <MemoBlock title="Thesis" value={memo.thesis} />
            <MemoBlock title="Bull case" value={memo.bull_case} />
            <MemoBlock title="Base case" value={memo.base_case} />
            <MemoBlock title="Bear case" value={memo.bear_case} />
            <MemoBlock title="Thesis breakers" value={memo.thesis_breakers} />
            <MemoBlock title="Risk notes" value={memo.risk_assessment} />
          </section>

          <section className="mt-5 rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Scorecard
            </p>
            <div className="mt-3 grid gap-3 lg:grid-cols-5">
              {scoreData.scorecard.map((item) => (
                <div
                  key={item.name}
                  className="rounded-md bg-zinc-50 p-3 dark:bg-zinc-900"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-medium text-zinc-500">{item.name}</p>
                    <p className="font-mono text-sm">{score(item.score)}</p>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-zinc-500">{item.notes}</p>
                </div>
              ))}
            </div>
          </section>

          <div className="mt-5 flex flex-wrap gap-2 text-xs text-zinc-500">
            <span>{memo.memo_date}</span>
            <span>{memo.model_version_label ?? "Unversioned model"}</span>
            <span>{formatLabel(memo.classification)}</span>
          </div>
        </div>
      )}
    </Modal>
  );
}

function AnalysisLayer({
  rows,
  title,
}: {
  rows: [string, string][];
  title: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <div className="mt-3 space-y-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <p className="text-xs font-medium text-zinc-500">{label}</p>
            <p className="mt-1 text-sm leading-5 text-zinc-800 dark:text-zinc-200">
              {value}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function MemoBlock({ title, value }: { title: string; value: string | null }) {
  return (
    <div className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <p className="mt-2 min-h-10 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
        {value || "Not recorded"}
      </p>
    </div>
  );
}

type MemoScores = {
  action?: string;
  composite_score?: string;
  confidence_score?: string;
  recommended_weight?: string;
  scorecard: TickerAnalysis["scorecard"];
};

function parseMemoScores(memo: TickerMemo | null): MemoScores {
  if (!memo) {
    return { scorecard: [] };
  }
  const scorecard = Array.isArray(memo.scores.scorecard)
    ? memo.scores.scorecard.filter(isTickerScore)
    : [];

  return {
    action: stringScoreValue(memo.scores.action),
    composite_score: stringScoreValue(memo.scores.composite_score),
    confidence_score: stringScoreValue(memo.scores.confidence_score),
    recommended_weight: stringScoreValue(memo.scores.recommended_weight),
    scorecard,
  };
}

function isTickerScore(value: unknown): value is TickerAnalysis["scorecard"][number] {
  if (!value || typeof value !== "object") {
    return false;
  }
  const item = value as Record<string, unknown>;
  return (
    typeof item.name === "string" &&
    typeof item.score === "string" &&
    typeof item.weight === "string" &&
    typeof item.notes === "string"
  );
}

function stringScoreValue(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function metricText(scores: MemoScores, metricName: string) {
  const item = scores.scorecard.find((scoreItem) => scoreItem.name === metricName);
  if (!item) {
    return "Not scored";
  }
  return `${score(item.score)}/100 - ${item.notes}`;
}

function MetricField({ label, name }: { label: string; name: string }) {
  return (
    <Field label={label}>
      <input name={name} type="number" step="0.01" className={inputClassName} />
    </Field>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
      {label}
      {children}
    </label>
  );
}

function buildPayload(formData: FormData): TickerAnalysisInput {
  return {
    instrument: {
      ticker: textValue(formData, "ticker"),
      name: textValue(formData, "name"),
      asset_class: textValue(formData, "asset_class") as TickerAnalysisInput["instrument"]["asset_class"],
      exchange: optionalTextValue(formData, "exchange"),
      currency: "USD",
      sector: optionalTextValue(formData, "sector"),
      industry: optionalTextValue(formData, "industry"),
    },
    metrics: {
      current_price: optionalNumberValue(formData, "current_price"),
      market_cap_billion: optionalNumberValue(formData, "market_cap_billion"),
      pe_ratio: optionalNumberValue(formData, "pe_ratio"),
      forward_pe: optionalNumberValue(formData, "forward_pe"),
      revenue_growth_pct: optionalNumberValue(formData, "revenue_growth_pct"),
      earnings_growth_pct: optionalNumberValue(formData, "earnings_growth_pct"),
      free_cash_flow_yield_pct: optionalNumberValue(formData, "free_cash_flow_yield_pct"),
      net_margin_pct: optionalNumberValue(formData, "net_margin_pct"),
      debt_to_equity: optionalNumberValue(formData, "debt_to_equity"),
      price_vs_200d_pct: optionalNumberValue(formData, "price_vs_200d_pct"),
      relative_strength_6m_pct: optionalNumberValue(formData, "relative_strength_6m_pct"),
      volatility_30d_pct: optionalNumberValue(formData, "volatility_30d_pct"),
    },
    time_horizon: textValue(formData, "time_horizon") || "6-18 months",
    investment_question: optionalTextValue(formData, "investment_question"),
    thesis: textValue(formData, "thesis"),
    bull_case: optionalTextValue(formData, "bull_case"),
    base_case: optionalTextValue(formData, "base_case"),
    bear_case: optionalTextValue(formData, "bear_case"),
    thesis_breakers: optionalTextValue(formData, "thesis_breakers"),
    risk_notes: optionalTextValue(formData, "risk_notes"),
    source_reference: optionalTextValue(formData, "source_reference"),
  };
}

function fillFormFromPrefill(form: HTMLFormElement, prefill: TickerPrefill) {
  const values: Record<string, string | undefined | null> = {
    ticker: prefill.instrument.ticker,
    name: prefill.instrument.name,
    asset_class: prefill.instrument.asset_class,
    exchange: prefill.instrument.exchange,
    sector: prefill.instrument.sector,
    industry: prefill.instrument.industry,
    source_reference: prefill.source_reference,
    current_price: prefill.metrics.current_price,
    market_cap_billion: prefill.metrics.market_cap_billion,
    pe_ratio: prefill.metrics.pe_ratio,
    forward_pe: prefill.metrics.forward_pe,
    revenue_growth_pct: prefill.metrics.revenue_growth_pct,
    earnings_growth_pct: prefill.metrics.earnings_growth_pct,
    free_cash_flow_yield_pct: prefill.metrics.free_cash_flow_yield_pct,
    net_margin_pct: prefill.metrics.net_margin_pct,
    debt_to_equity: prefill.metrics.debt_to_equity,
    price_vs_200d_pct: prefill.metrics.price_vs_200d_pct,
    relative_strength_6m_pct: prefill.metrics.relative_strength_6m_pct,
    volatility_30d_pct: prefill.metrics.volatility_30d_pct,
  };

  Object.entries(values).forEach(([name, value]) => {
    setFormValue(form, name, value);
  });
}

function setFormValue(
  form: HTMLFormElement,
  name: string,
  value: string | undefined | null,
) {
  if (value === undefined || value === null) {
    return;
  }
  const element = form.elements.namedItem(name);
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
  ) {
    element.value = value;
  }
}

function textValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function optionalTextValue(formData: FormData, key: string) {
  const value = textValue(formData, key);
  return value.length > 0 ? value : undefined;
}

function optionalNumberValue(formData: FormData, key: string) {
  const value = textValue(formData, key);
  return value.length > 0 ? value : undefined;
}

function formatLabel(value: string) {
  return value
    .split(/[_ -]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const inputClassName =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-zinc-950 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:border-zinc-200";

const inputClassNameNoMargin =
  "w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-zinc-950 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:border-zinc-200";

const buttonClassName =
  "rounded-md bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-300 dark:disabled:bg-zinc-700 dark:disabled:text-zinc-400";

const secondaryButtonClassName =
  "shrink-0 rounded-md border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-400 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900 dark:disabled:bg-zinc-900 dark:disabled:text-zinc-600";
