"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { TickerCombobox } from "@/components/ticker/TickerCombobox";
import { Modal } from "@/components/ui/Modal";
import { toast } from "@/components/ui/ToastProvider";
import {
  createTickerAIDraft,
  createTickerAnalysis,
  getTickerMemo,
  getTickerMLReport,
  getTickerPrefill,
  runResearchDataPipeline,
  type TickerAIDraft,
  type TickerAIDraftInput,
  type TickerAnalysis,
  type TickerAnalysisInput,
  type TickerMLReport,
  type TickerMemo,
  type TickerMemoSummary,
  type TickerPrefill,
} from "@/lib/api";

type TickerAnalystProps = {
  recentMemos: TickerMemoSummary[];
  isUnavailable: boolean;
};

type WorkflowStep = "ticker" | "prefill" | "questions" | "output";

const workflowSteps: { key: WorkflowStep; label: string }[] = [
  { key: "ticker", label: "Ticker" },
  { key: "prefill", label: "Prefill" },
  { key: "questions", label: "Questions" },
  { key: "output", label: "Output" },
];

const scoreFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

function score(value: string | null | undefined) {
  if (!value) return "-";
  return scoreFormatter.format(Number(value));
}

function weight(value: string) {
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function ratioPercent(value: string | null | undefined) {
  if (!value) return "-";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

export function TickerAnalyst({ recentMemos, isUnavailable }: TickerAnalystProps) {
  const router = useRouter();
  const formRef = useRef<HTMLFormElement>(null);
  const [mode, setMode] = useState<"history" | "workflow">("history");
  const [step, setStep] = useState<WorkflowStep>("ticker");
  const [analysis, setAnalysis] = useState<TickerAnalysis | null>(null);
  const [mlReport, setMlReport] = useState<TickerMLReport | null>(null);
  const [aiDraft, setAiDraft] = useState<TickerAIDraft | null>(null);
  const [baseAnalysisInput, setBaseAnalysisInput] =
    useState<TickerAnalysisInput | null>(null);
  const [prefillData, setPrefillData] = useState<TickerPrefill | null>(null);
  const [prefillWarnings, setPrefillWarnings] = useState<string[]>([]);
  const [selectedMemo, setSelectedMemo] = useState<TickerMemo | null>(null);
  const [memoLoadingId, setMemoLoadingId] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    "prefill" | "draft" | "model" | "ml-pipeline" | null
  >(null);
  const [error, setError] = useState<string | null>(
    isUnavailable ? "Ticker workspace could not be loaded yet." : null,
  );

  function startNewAnalysis() {
    setMode("workflow");
    setStep("ticker");
    setAnalysis(null);
    setMlReport(null);
    setAiDraft(null);
    setBaseAnalysisInput(null);
    setPrefillData(null);
    setPrefillWarnings([]);
    setError(null);
    window.setTimeout(() => formRef.current?.reset(), 0);
  }

  function returnToHistory() {
    setMode("history");
    setStep("ticker");
    setAnalysis(null);
    setMlReport(null);
    setAiDraft(null);
    setBaseAnalysisInput(null);
    setPrefillData(null);
    setPrefillWarnings([]);
    setError(null);
    router.refresh();
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

  async function handlePrefill() {
    const form = formRef.current;
    if (!form) return;

    const tickerFormData = new FormData(form);
    const ticker = textValue(tickerFormData, "ticker");
    const market = textValue(tickerFormData, "market");
    if (!ticker) {
      setError("Enter a ticker first.");
      return;
    }

    setPendingAction("prefill");
    setError(null);
    setPrefillWarnings([]);

    try {
      const result = await getTickerPrefill(ticker, market);
      fillFormFromPrefill(form, result);
      setPrefillData(result);
      setPrefillWarnings(result.source_warnings.filter(isAnalystVisibleWarning));
      setStep("prefill");
    } catch {
      setError("Ticker prefill was not available.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleGenerateDraft() {
    const form = formRef.current;
    if (!form) return;

    const formData = new FormData(form);
    const ticker = textValue(formData, "ticker");
    const name = textValue(formData, "name");
    if (!ticker || !name) {
      setError("Ticker details are required before drafting.");
      return;
    }

    setPendingAction("draft");
    setError(null);

    try {
      setBaseAnalysisInput(buildPayload(formData));
      const draft = await createTickerAIDraft(
        buildAIDraftPayload(formData, prefillWarnings),
      );
      setAiDraft(draft);
      setStep("questions");
    } catch (draftError) {
      const message =
        draftError instanceof Error && draftError.message
          ? draftError.message
          : "AI draft was not available.";
      setError(message);
    } finally {
      setPendingAction(null);
    }
  }

  async function handleRunModel() {
    const form = formRef.current;
    if (!form) return;

    const formData = new FormData(form);
    if (!textValue(formData, "thesis")) {
      setError("Thesis is required before running the model output.");
      return;
    }

    setPendingAction("model");
    setError(null);

    try {
      const payload = buildPayloadFromDraftStep(baseAnalysisInput, formData);
      const result = await createTickerAnalysis(payload);
      setAnalysis(result);
      try {
        const report = await getTickerMLReport(payload.instrument.ticker);
        setMlReport(report);
      } catch {
        setMlReport(null);
      }
      setStep("output");
      router.refresh();
    } catch {
      setError("Model output was not saved.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handlePrepareMLLayer() {
    const ticker = analysis?.memo.instrument.ticker ?? baseAnalysisInput?.instrument.ticker;
    if (!ticker) {
      toast.error("Run a ticker analysis before preparing the ML layer.");
      return;
    }

    const horizonDays = mlReportHorizon(mlReport) ?? 63;
    setPendingAction("ml-pipeline");
    setError(null);

    try {
      const result = await runResearchDataPipeline({
        tickers: analysisTrainingUniverse(ticker, recentMemos),
        benchmark_ticker: "SPY",
        start_date: dateYearsAgoValue(5),
        end_date: todayDateValue(),
        horizon_days: horizonDays,
        source: "yahoo",
        train_model: true,
      });
      const nextReport = await getTickerMLReport(ticker, horizonDays);
      setMlReport(nextReport);
      if (result.model_version_id) {
        toast.success(`${ticker} ML layer prepared for ${horizonDays}d horizon.`);
      } else if (result.warnings.length > 0) {
        toast.error("ML pipeline finished with items to review.");
      } else {
        toast.success(`${ticker} ML data prepared.`);
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "ML layer could not be prepared.",
      );
    } finally {
      setPendingAction(null);
    }
  }

  if (mode === "history") {
    return (
      <div className="mx-auto max-w-[1560px] space-y-5">
        <HistoryHeader onNewAnalysis={startNewAnalysis} />
        {error && <ErrorNotice message={error} />}
        <MemoIndex
          loadingId={memoLoadingId}
          memos={recentMemos}
          onOpenMemo={handleOpenMemo}
        />
        <TickerMemoModal memo={selectedMemo} onClose={() => setSelectedMemo(null)} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <WorkflowHeader
        activeStep={step}
        onCancel={returnToHistory}
        onNewAnalysis={startNewAnalysis}
      />
      {error && <ErrorNotice message={error} />}

      <form ref={formRef} onSubmit={preventSubmit} className="space-y-5">
        <WorkflowStepper activeStep={step} />

        {step === "ticker" && (
          <WorkflowPanel eyebrow="Step 1" title="Ticker Intake">
            <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px_220px]">
              <Field label="Ticker">
                <TickerCombobox
                  name="ticker"
                  required
                  autoFocus
                  className={inputClassName}
                />
              </Field>
              <Field label="Market">
                <select name="market" defaultValue="auto" className={inputClassName}>
                  <option value="auto">Auto</option>
                  <option value="US">US</option>
                  <option value="NG">Nigeria</option>
                </select>
              </Field>
              <Field label="Time Horizon">
                <input
                  name="time_horizon"
                  defaultValue="6-18 months"
                  className={inputClassName}
                />
              </Field>
            </div>
            <WorkflowActions
              backLabel="Cancel"
              nextLabel={pendingAction === "prefill" ? "Fetching..." : "Continue"}
              nextDisabled={pendingAction !== null}
              onBack={returnToHistory}
              onNext={handlePrefill}
            />
          </WorkflowPanel>
        )}

        {step === "prefill" && (
          <WorkflowPanel eyebrow="Step 2" title="Prefill Review">
            <IdentityFields prefill={prefillData} />
            <MetricFields metrics={prefillData?.metrics} />
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="Time Horizon">
                <input
                  name="time_horizon"
                  defaultValue={baseAnalysisInput?.time_horizon ?? "6-18 months"}
                  className={inputClassName}
                />
              </Field>
              <Field label="Source Reference">
                <input
                  name="source_reference"
                  defaultValue={prefillData?.source_reference}
                  className={inputClassName}
                />
              </Field>
            </div>
            {prefillWarnings.length > 0 && <WarningNotice warnings={prefillWarnings} />}
            <WorkflowActions
              backLabel="Back"
              nextLabel={pendingAction === "draft" ? "Drafting..." : "Continue"}
              nextDisabled={pendingAction !== null}
              onBack={() => setStep("ticker")}
              onNext={handleGenerateDraft}
            />
          </WorkflowPanel>
        )}

        {step === "questions" && (
          <WorkflowPanel eyebrow="Step 3" title="Analyst Questions">
            {aiDraft && <AIDraftPanel draft={aiDraft} />}
            <MemoFields draft={aiDraft} />
            <WorkflowActions
              backLabel="Back"
              nextLabel={pendingAction === "model" ? "Running..." : "Continue"}
              nextDisabled={pendingAction !== null}
              onBack={() => setStep("prefill")}
              onNext={handleRunModel}
            />
          </WorkflowPanel>
        )}

        {step === "output" && (
          <WorkflowPanel eyebrow="Step 4" title="Model Output">
            <AnalysisPanel
              analysis={analysis}
              mlReport={mlReport}
              mlPipelinePending={pendingAction === "ml-pipeline"}
              onPrepareMLLayer={handlePrepareMLLayer}
            />
            <WorkflowActions
              backLabel="Previous Analyses"
              nextLabel="New Analysis"
              onBack={returnToHistory}
              onNext={startNewAnalysis}
            />
          </WorkflowPanel>
        )}
      </form>

      <TickerMemoModal memo={selectedMemo} onClose={() => setSelectedMemo(null)} />
    </div>
  );
}

function HistoryHeader({ onNewAnalysis }: { onNewAnalysis: () => void }) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Ticker Analyst
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-normal">
          Previous Analysis
        </h2>
      </div>
      <button type="button" onClick={onNewAnalysis} className={buttonClassName}>
        New Analysis
      </button>
    </section>
  );
}

function WorkflowHeader({
  activeStep,
  onCancel,
  onNewAnalysis,
}: {
  activeStep: WorkflowStep;
  onCancel: () => void;
  onNewAnalysis: () => void;
}) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Ticker Analyst
        </p>
        <h2 className="mt-1 text-xl font-semibold tracking-normal">
          {workflowSteps.find((item) => item.key === activeStep)?.label}
        </h2>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onCancel} className={secondaryButtonClassName}>
          Previous Analyses
        </button>
        <button type="button" onClick={onNewAnalysis} className={secondaryButtonClassName}>
          Restart
        </button>
      </div>
    </section>
  );
}

function WorkflowStepper({ activeStep }: { activeStep: WorkflowStep }) {
  const activeIndex = workflowSteps.findIndex((item) => item.key === activeStep);

  return (
    <div className="grid gap-2 sm:grid-cols-4">
      {workflowSteps.map((item, index) => {
        const active = item.key === activeStep;
        const complete = index < activeIndex;
        return (
          <div
            key={item.key}
            className={`rounded-lg border px-3 py-3 ${
              active
                ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                : complete
                  ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                  : "border-zinc-200 bg-white text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950"
            }`}
          >
            <p className="text-xs font-semibold uppercase tracking-wide">
              Step {index + 1}
            </p>
            <p className="mt-1 text-sm font-medium">{item.label}</p>
          </div>
        );
      })}
    </div>
  );
}

function WorkflowPanel({
  children,
  eyebrow,
  title,
}: {
  children: React.ReactNode;
  eyebrow: string;
  title: string;
}) {
  return (
    <section className="space-y-5 rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          {eyebrow}
        </p>
        <h3 className="mt-1 text-base font-semibold">{title}</h3>
      </div>
      {children}
    </section>
  );
}

function WorkflowActions({
  backLabel,
  nextDisabled = false,
  nextLabel,
  onBack,
  onNext,
}: {
  backLabel: string;
  nextDisabled?: boolean;
  nextLabel: string;
  onBack: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-100 pt-4 dark:border-zinc-900">
      <button type="button" onClick={onBack} className={secondaryButtonClassName}>
        {backLabel}
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={nextDisabled}
        className={buttonClassName}
      >
        {nextLabel}
      </button>
    </div>
  );
}

function MemoIndex({
  loadingId,
  memos,
  onOpenMemo,
}: {
  loadingId: string | null;
  memos: TickerMemoSummary[];
  onOpenMemo: (memoId: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr>
              <Th>Ticker</Th>
              <Th>Name</Th>
              <Th>Classification</Th>
              <Th>Action</Th>
              <Th>Composite</Th>
              <Th>Date</Th>
            </tr>
          </thead>
          <tbody>
            {memos.map((memo) => (
              <tr key={memo.id}>
                <Td emphasis>
                  <button
                    type="button"
                    onClick={() => onOpenMemo(memo.id)}
                    className="font-semibold text-zinc-950 underline-offset-4 hover:underline dark:text-zinc-50"
                  >
                    {memo.ticker}
                  </button>
                </Td>
                <Td>{memo.name}</Td>
                <Td>{formatLabel(memo.classification)}</Td>
                <Td>{memo.action ? formatLabel(memo.action) : "-"}</Td>
                <Td align="right">
                  {loadingId === memo.id ? "..." : score(memo.composite_score)}
                </Td>
                <Td>{memo.memo_date}</Td>
              </tr>
            ))}
            {memos.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No previous analysis
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function IdentityFields({ prefill }: { prefill: TickerPrefill | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-4">
      <Field label="Ticker">
        <TickerCombobox
          name="ticker"
          required
          defaultValue={prefill?.instrument.ticker}
          className={inputClassName}
        />
      </Field>
      <Field label="Name">
        <input
          name="name"
          required
          defaultValue={prefill?.instrument.name}
          className={inputClassName}
        />
      </Field>
      <Field label="Asset Class">
        <select
          name="asset_class"
          defaultValue={prefill?.instrument.asset_class ?? "equity"}
          className={inputClassName}
        >
          <option value="equity">Equity</option>
          <option value="etf">ETF</option>
          <option value="bond">Bond</option>
          <option value="commodity">Commodity</option>
          <option value="cash_equivalent">Cash Equivalent</option>
          <option value="other">Other</option>
        </select>
      </Field>
      <Field label="Currency">
        <input
          name="currency"
          defaultValue={prefill?.instrument.currency ?? "USD"}
          className={`${inputClassName} uppercase`}
        />
      </Field>
      <Field label="Exchange">
        <input
          name="exchange"
          defaultValue={prefill?.instrument.exchange ?? ""}
          className={inputClassName}
        />
      </Field>
      <Field label="Sector">
        <input
          name="sector"
          defaultValue={prefill?.instrument.sector ?? ""}
          className={inputClassName}
        />
      </Field>
      <Field label="Industry">
        <input
          name="industry"
          defaultValue={prefill?.instrument.industry ?? ""}
          className={inputClassName}
        />
      </Field>
    </div>
  );
}

function MetricFields({ metrics }: { metrics?: TickerAnalysisInput["metrics"] }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricField label="Price" name="current_price" value={metrics?.current_price} />
      <MetricField label="Market Cap B" name="market_cap_billion" value={metrics?.market_cap_billion} />
      <MetricField label="P/E" name="pe_ratio" value={metrics?.pe_ratio} />
      <MetricField label="Forward P/E" name="forward_pe" value={metrics?.forward_pe} />
      <MetricField label="Revenue Growth %" name="revenue_growth_pct" value={metrics?.revenue_growth_pct} />
      <MetricField label="Earnings Growth %" name="earnings_growth_pct" value={metrics?.earnings_growth_pct} />
      <MetricField label="FCF Yield %" name="free_cash_flow_yield_pct" value={metrics?.free_cash_flow_yield_pct} />
      <MetricField label="Net Margin %" name="net_margin_pct" value={metrics?.net_margin_pct} />
      <MetricField label="Debt / Equity" name="debt_to_equity" value={metrics?.debt_to_equity} />
      <MetricField label="Price vs 200D %" name="price_vs_200d_pct" value={metrics?.price_vs_200d_pct} />
      <MetricField label="6M Rel. Strength %" name="relative_strength_6m_pct" value={metrics?.relative_strength_6m_pct} />
      <MetricField label="30D Volatility %" name="volatility_30d_pct" value={metrics?.volatility_30d_pct} />
    </div>
  );
}

function MemoFields({ draft }: { draft: TickerAIDraft | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Field label="Investment Question">
        <textarea
          name="investment_question"
          rows={3}
          defaultValue={draft?.investment_question}
          className={inputClassName}
        />
      </Field>
      <Field label="Thesis">
        <textarea
          name="thesis"
          required
          rows={3}
          defaultValue={draft?.thesis}
          className={inputClassName}
        />
      </Field>
      <Field label="Bull Case">
        <textarea
          name="bull_case"
          rows={3}
          defaultValue={draft?.bull_case}
          className={inputClassName}
        />
      </Field>
      <Field label="Base Case">
        <textarea
          name="base_case"
          rows={3}
          defaultValue={draft?.base_case}
          className={inputClassName}
        />
      </Field>
      <Field label="Bear Case">
        <textarea
          name="bear_case"
          rows={3}
          defaultValue={draft?.bear_case}
          className={inputClassName}
        />
      </Field>
      <Field label="Thesis Breakers">
        <textarea
          name="thesis_breakers"
          rows={3}
          defaultValue={draft?.thesis_breakers}
          className={inputClassName}
        />
      </Field>
      <Field label="Risk Notes">
        <textarea
          name="risk_notes"
          rows={3}
          defaultValue={draft?.risk_notes}
          className={inputClassName}
        />
      </Field>
    </div>
  );
}

function AIDraftPanel({ draft }: { draft: TickerAIDraft }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_0.75fr]">
      <section className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Questions
        </p>
        <div className="mt-3 space-y-3">
          {draft.analyst_questions.map((question) => (
            <p key={question} className="text-sm leading-6 text-zinc-700 dark:text-zinc-300">
              {question}
            </p>
          ))}
        </div>
      </section>
      <section className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Notes
        </p>
        <p className="mt-3 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
          {draft.confidence_notes}
        </p>
        {draft.missing_data_warnings.length > 0 && (
          <div className="mt-3 space-y-2">
            {draft.missing_data_warnings.map((warning) => (
              <p key={warning} className="text-xs leading-5 text-amber-700 dark:text-amber-300">
                {warning}
              </p>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function AnalysisPanel({
  analysis,
  mlPipelinePending,
  mlReport,
  onPrepareMLLayer,
}: {
  analysis: TickerAnalysis | null;
  mlPipelinePending: boolean;
  mlReport: TickerMLReport | null;
  onPrepareMLLayer: () => void;
}) {
  if (!analysis) {
    return (
      <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900">
        <p className="text-sm text-zinc-500">No model output yet</p>
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
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            {analysis.memo.instrument.ticker}
          </p>
          <h3 className="mt-1 text-base font-semibold">
            {formatLabel(analysis.action)}
          </h3>
        </div>
        <span className="rounded-md bg-zinc-950 px-2.5 py-1.5 text-xs font-medium text-white dark:bg-zinc-100 dark:text-zinc-950">
          {formatLabel(analysis.classification)}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-4">
        {metrics.map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg border border-zinc-100 bg-zinc-50 px-3.5 py-3 dark:border-zinc-900 dark:bg-zinc-900"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              {label}
            </p>
            <p className="mt-2 text-2xl font-semibold tracking-normal">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-3 lg:grid-cols-5">
        {analysis.scorecard.map((item) => (
          <div key={item.name} className="rounded-lg border border-zinc-100 p-3 dark:border-zinc-900">
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

      <p className="rounded-lg bg-zinc-50 px-3 py-2 text-sm text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
        {analysis.evidence_summary}
      </p>

      <MLReportPanel
        onPrepareMLLayer={onPrepareMLLayer}
        preparePending={mlPipelinePending}
        report={mlReport}
      />
    </div>
  );
}

function MLReportPanel({
  onPrepareMLLayer,
  preparePending,
  report,
}: {
  onPrepareMLLayer: () => void;
  preparePending: boolean;
  report: TickerMLReport | null;
}) {
  if (!report) {
    return (
      <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900">
        <p className="text-sm text-zinc-500">ML report unavailable</p>
      </div>
    );
  }

  const prediction = report.prediction;
  const portfolioFit = report.portfolio_fit;
  const comparisonMetrics = report.comparative?.metrics.slice(0, 5) ?? [];
  const needsPipeline = report.warnings.some(isMLPipelineWarning);
  const horizonDays = mlReportHorizon(report) ?? 63;

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
      <section className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Comparative
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-xs">
            <thead>
              <tr>
                <Th>Metric</Th>
                <Th>Value</Th>
                <Th>History</Th>
                <Th>Sector</Th>
                <Th>Universe</Th>
              </tr>
            </thead>
            <tbody>
              {comparisonMetrics.map((metric) => (
                <tr key={metric.metric}>
                  <Td>{formatFeature(metric.metric)}</Td>
                  <Td>{score(metric.value)}</Td>
                  <Td>{score(metric.history_percentile)}</Td>
                  <Td>{score(metric.sector_percentile)}</Td>
                  <Td>{score(metric.universe_percentile)}</Td>
                </tr>
              ))}
              {comparisonMetrics.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-5 py-6 text-center text-zinc-500">
                    No comparative ranks
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-zinc-100 p-4 dark:border-zinc-900">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Predictive
        </p>
        {prediction ? (
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <MetricCard label="Expected relative" value={`${score(prediction.expected_relative_return_pct)}%`} />
            <MetricCard label="Downside p05" value={`${score(prediction.downside_p05_relative_return_pct)}%`} />
            <MetricCard label="Outperform prob." value={ratioPercent(prediction.probability_outperform)} />
            <MetricCard label="ML confidence" value={`${score(prediction.confidence_score)}%`} />
          </div>
        ) : (
          <p className="mt-3 text-sm text-zinc-500">Prediction pending</p>
        )}

        {portfolioFit && (
          <div className="mt-4 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-900">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">
                {portfolioFit.improves_portfolio ? "Improves portfolio" : "Does not improve portfolio"}
              </p>
              <span className="font-mono text-sm">
                {score(portfolioFit.portfolio_fit_score)}
              </span>
            </div>
            <div className="mt-3 grid gap-2 text-xs text-zinc-500 sm:grid-cols-3">
              <span>Current {score(portfolioFit.current_position_weight)}%</span>
              <span>Pro forma {score(portfolioFit.pro_forma_weight)}%</span>
              <span>Sector {score(portfolioFit.sector_exposure_after)}%</span>
            </div>
          </div>
        )}

        {prediction?.drivers && prediction.drivers.length > 0 && (
          <div className="mt-4 space-y-2">
            {prediction.drivers.map((driver) => (
              <div
                key={driver.feature}
                className="flex items-center justify-between gap-3 text-xs text-zinc-500"
              >
                <span>{formatFeature(driver.feature)}</span>
                <span className="font-mono">{driver.contribution_pct.toFixed(2)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {report.warnings.length > 0 && (
        <div className="xl:col-span-2">
          <WarningNotice
            action={
              needsPipeline
                ? {
                    href: `/research-lab?ticker=${encodeURIComponent(report.ticker)}&horizon=${horizonDays}`,
                    label: preparePending ? "Preparing..." : "Prepare ML layer",
                    onClick: onPrepareMLLayer,
                    pending: preparePending,
                  }
                : undefined
            }
            warnings={report.warnings}
          />
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2.5 dark:border-zinc-900 dark:bg-zinc-900">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
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
  const persistedReport = scoreData.ml_report;
  const comparativeRows = persistedReport?.comparative?.metrics.length
    ? persistedReport.comparative.metrics.slice(0, 4).map((metric) => [
        formatFeature(metric.metric),
        `History ${score(metric.history_percentile)}, sector ${score(metric.sector_percentile)}, universe ${score(metric.universe_percentile)}`,
      ] as [string, string])
    : ([
        ["History", "No persisted comparative snapshot"],
        ["Sector", "No persisted sector rank"],
        ["Peers", "No persisted peer rank"],
        ["Universe", "No persisted universe rank"],
      ] as [string, string][]);
  const predictiveRows: [string, string][] = persistedReport?.prediction
    ? [
        [
          "Expected return",
          `${score(persistedReport.prediction.expected_relative_return_pct)}% relative`,
        ],
        [
          "Downside distribution",
          `${score(persistedReport.prediction.downside_p05_relative_return_pct)}% p05`,
        ],
        [
          "Model confidence",
          `${score(persistedReport.prediction.confidence_score)}%`,
        ],
        [
          "Portfolio improvement",
          persistedReport.portfolio_fit?.improves_portfolio
            ? `Yes, fit ${score(persistedReport.portfolio_fit.portfolio_fit_score)}`
            : `No, fit ${score(persistedReport.portfolio_fit?.portfolio_fit_score)}`,
        ],
      ]
    : [
        ["Expected return", "No persisted prediction"],
        ["Downside distribution", "No persisted downside estimate"],
        ["Model confidence", score(scoreData.confidence_score)],
        ["Portfolio improvement", "No persisted portfolio-fit result"],
      ];

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
              rows={comparativeRows}
            />
            <AnalysisLayer
              title="Predictive"
              rows={predictiveRows}
            />
          </section>

          {persistedReport?.warnings && persistedReport.warnings.length > 0 && (
            <div className="mt-5">
              <WarningNotice warnings={persistedReport.warnings} />
            </div>
          )}

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

function WarningNotice({
  action,
  warnings,
}: {
  action?: {
    href: string;
    label: string;
    onClick: () => void;
    pending: boolean;
  };
  warnings: string[];
}) {
  const visibleWarnings = warnings
    .map(formatAnalystWarning)
    .filter((warning): warning is string => Boolean(warning));

  if (visibleWarnings.length === 0) {
    return null;
  }

  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
      <div className="space-y-1.5">
        {visibleWarnings.map((warning, index) => (
          <p key={`${warning}-${index}`}>{warning}</p>
        ))}
      </div>
      {action && (
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={action.onClick}
            disabled={action.pending}
            className={buttonClassName}
          >
            {action.label}
          </button>
          <Link href={action.href} className={secondaryButtonClassName}>
            Open Research Lab
          </Link>
        </div>
      )}
    </div>
  );
}

function formatAnalystWarning(warning: string) {
  const trimmed = warning.trim();
  if (!trimmed || !isAnalystVisibleWarning(trimmed)) {
    return null;
  }

  if (trimmed === "Comparative analysis needs price feature snapshots.") {
    return "Prepare the ML layer to build price-feature snapshots and unlock comparative ranks.";
  }

  const predictiveModelMatch = trimmed.match(
    /^No predictive model found for (\d+)-day horizon\.$/,
  );
  if (predictiveModelMatch) {
    return `Prepare the ML layer with ${predictiveModelMatch[1]}-day horizon to unlock predictive output.`;
  }

  if (trimmed === "Portfolio fit needs an instrument record and portfolio state.") {
    return "Portfolio fit will appear after this ticker is linked to your portfolio state.";
  }

  return trimmed;
}

function isAnalystVisibleWarning(warning: string) {
  const normalized = warning.trim().toLowerCase();
  if (normalized.includes("not available for this api key or plan")) {
    return false;
  }
  if (normalized.includes("was not found by provider")) {
    return false;
  }
  if (normalized.includes("sec companyfacts skipped")) {
    return false;
  }
  if (
    normalized.includes(" returned 404") &&
    ["/v2/", "/v3/", "/stocks/", "/tiingo/", "/companies", "/etfs"].some((prefix) =>
      normalized.startsWith(prefix),
    )
  ) {
    return false;
  }
  return true;
}

function isMLPipelineWarning(warning: string) {
  return (
    warning === "Comparative analysis needs price feature snapshots." ||
    /^No predictive model found for \d+-day horizon\.$/.test(warning)
  );
}

function mlReportHorizon(report: TickerMLReport | null) {
  if (report?.prediction?.horizon_days) {
    return report.prediction.horizon_days;
  }

  for (const warning of report?.warnings ?? []) {
    const match = warning.match(/^No predictive model found for (\d+)-day horizon\.$/);
    if (match) {
      return Number(match[1]);
    }
  }

  return null;
}

function analysisTrainingUniverse(
  ticker: string,
  recentMemos: TickerMemoSummary[],
) {
  return uniqueTickers([
    ticker,
    ...recentMemos.map((memo) => memo.ticker),
  ]).filter((symbol) => symbol !== "SPY");
}

function uniqueTickers(tickers: string[]) {
  return Array.from(
    new Set(
      tickers
        .map((ticker) => ticker.trim().toUpperCase())
        .filter(Boolean),
    ),
  );
}

function ErrorNotice({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      {message}
    </div>
  );
}

function MetricField({
  label,
  name,
  value,
}: {
  label: string;
  name: string;
  value?: string | null;
}) {
  return (
    <Field label={label}>
      <input
        name={name}
        type="number"
        step="0.01"
        defaultValue={value ?? ""}
        className={inputClassName}
      />
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

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-zinc-100 bg-zinc-50/80 px-5 py-3 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-900 dark:bg-zinc-900/50">
      {children}
    </th>
  );
}

function Td({
  align = "left",
  children,
  emphasis = false,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
  emphasis?: boolean;
}) {
  return (
    <td
      className={`border-b border-zinc-100 px-5 py-3.5 dark:border-zinc-900 ${
        align === "right" ? "text-right" : "text-left"
      } ${
        emphasis
          ? "font-medium text-zinc-950 dark:text-zinc-50"
          : "text-zinc-700 dark:text-zinc-300"
      }`}
    >
      {children}
    </td>
  );
}

type MemoScores = {
  action?: string;
  composite_score?: string;
  confidence_score?: string;
  recommended_weight?: string;
  ml_report?: TickerMLReport;
  scorecard: TickerAnalysis["scorecard"];
};

function parseMemoScores(memo: TickerMemo | null): MemoScores {
  if (!memo) return { scorecard: [] };
  const scorecard = Array.isArray(memo.scores.scorecard)
    ? memo.scores.scorecard.filter(isTickerScore)
    : [];

  return {
    action: stringScoreValue(memo.scores.action),
    composite_score: stringScoreValue(memo.scores.composite_score),
    confidence_score: stringScoreValue(memo.scores.confidence_score),
    recommended_weight: stringScoreValue(memo.scores.recommended_weight),
    ml_report: isTickerMLReport(memo.scores.ml_report)
      ? memo.scores.ml_report
      : undefined,
    scorecard,
  };
}

function isTickerScore(value: unknown): value is TickerAnalysis["scorecard"][number] {
  if (!value || typeof value !== "object") return false;
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

function isTickerMLReport(value: unknown): value is TickerMLReport {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.ticker === "string" && Array.isArray(item.warnings);
}

function metricText(scores: MemoScores, metricName: string) {
  const item = scores.scorecard.find((scoreItem) => scoreItem.name === metricName);
  if (!item) return "Not scored";
  return `${score(item.score)}/100 - ${item.notes}`;
}

function buildPayload(formData: FormData): TickerAnalysisInput {
  return {
    instrument: buildInstrumentPayload(formData),
    metrics: buildMetricsPayload(formData),
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

function buildPayloadFromDraftStep(
  basePayload: TickerAnalysisInput | null,
  formData: FormData,
): TickerAnalysisInput {
  const memoPayload = {
    investment_question: optionalTextValue(formData, "investment_question"),
    thesis: textValue(formData, "thesis"),
    bull_case: optionalTextValue(formData, "bull_case"),
    base_case: optionalTextValue(formData, "base_case"),
    bear_case: optionalTextValue(formData, "bear_case"),
    thesis_breakers: optionalTextValue(formData, "thesis_breakers"),
    risk_notes: optionalTextValue(formData, "risk_notes"),
  };

  if (basePayload) {
    return {
      ...basePayload,
      ...memoPayload,
    };
  }

  return {
    instrument: {
      ticker: "",
      name: "",
      asset_class: "equity",
      currency: "USD",
    },
    metrics: {},
    time_horizon: "6-18 months",
    source_reference: undefined,
    ...memoPayload,
  };
}

function buildAIDraftPayload(
  formData: FormData,
  sourceWarnings: string[],
): TickerAIDraftInput {
  return {
    instrument: buildInstrumentPayload(formData),
    metrics: buildMetricsPayload(formData),
    time_horizon: textValue(formData, "time_horizon") || "6-18 months",
    source_reference: optionalTextValue(formData, "source_reference"),
    source_warnings: sourceWarnings,
    user_notes: [
      optionalTextValue(formData, "investment_question"),
      optionalTextValue(formData, "thesis"),
      optionalTextValue(formData, "risk_notes"),
    ]
      .filter(Boolean)
      .join("\n\n"),
  };
}

function buildInstrumentPayload(
  formData: FormData,
): TickerAnalysisInput["instrument"] {
  return {
    ticker: textValue(formData, "ticker"),
    name: textValue(formData, "name"),
    asset_class: textValue(formData, "asset_class") as TickerAnalysisInput["instrument"]["asset_class"],
    exchange: optionalTextValue(formData, "exchange"),
    currency: optionalTextValue(formData, "currency") ?? "USD",
    sector: optionalTextValue(formData, "sector"),
    industry: optionalTextValue(formData, "industry"),
  };
}

function buildMetricsPayload(formData: FormData): TickerAnalysisInput["metrics"] {
  return {
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
  };
}

function fillFormFromPrefill(form: HTMLFormElement, prefill: TickerPrefill) {
  const values: Record<string, string | undefined | null> = {
    ticker: prefill.instrument.ticker,
    name: prefill.instrument.name,
    asset_class: prefill.instrument.asset_class,
    currency: prefill.instrument.currency,
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

  Object.entries(values).forEach(([name, value]) => setFormValue(form, name, value));
}

function setFormValue(
  form: HTMLFormElement,
  name: string,
  value: string | undefined | null,
) {
  if (value === undefined || value === null) return;
  const element = form.elements.namedItem(name);
  if (
    element instanceof HTMLInputElement ||
    element instanceof HTMLTextAreaElement ||
    element instanceof HTMLSelectElement
  ) {
    element.value = value;
  }
}

function preventSubmit(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
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

function todayDateValue() {
  return new Date().toISOString().slice(0, 10);
}

function dateYearsAgoValue(years: number) {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  return date.toISOString().slice(0, 10);
}

function formatLabel(value: string) {
  return value
    .split(/[_ -]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatFeature(value: string) {
  return value
    .replace(/_pct$/, " %")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

const inputClassName =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-zinc-950 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:border-zinc-200";

const buttonClassName =
  "rounded-md bg-zinc-950 px-4 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-300 dark:disabled:bg-zinc-700 dark:disabled:text-zinc-400";

const secondaryButtonClassName =
  "shrink-0 rounded-md border border-zinc-200 px-3 py-2 text-sm font-medium text-zinc-700 transition hover:bg-zinc-50 disabled:cursor-not-allowed disabled:bg-zinc-100 disabled:text-zinc-400 dark:border-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-900 dark:disabled:bg-zinc-900 dark:disabled:text-zinc-600";
