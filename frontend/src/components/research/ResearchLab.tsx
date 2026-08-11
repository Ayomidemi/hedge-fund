"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  getResearchLabOverview,
  runResearchDataPipeline,
  type ResearchPipelineRun,
} from "@/lib/api";
import { BacktestsPanel } from "@/components/research/BacktestsPanel";
import { PipelineStepsPanel } from "@/components/research/PipelineStepsPanel";
import { RegimePanel } from "@/components/research/RegimePanel";
import {
  dateYearsAgoValue,
  parseTickerList,
  todayDateValue,
  uniqueTickers,
} from "@/components/research/research-lab-ui";
import type {
  ResearchActionItem,
  ResearchDataset,
  ResearchExperiment,
  ResearchFeatureSet,
  ResearchLabOverview,
  ResearchModel,
  ResearchNotebook,
  ResearchValidationCheck,
} from "@/lib/api";

type ResearchLabProps = {
  initialOverview: ResearchLabOverview | null;
  unavailable: boolean;
};

type LabTab =
  | "overview"
  | "datasets"
  | "features"
  | "notebooks"
  | "experiments"
  | "backtests"
  | "regime"
  | "models";

const tabs: { key: LabTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "datasets", label: "Datasets" },
  { key: "features", label: "Features" },
  { key: "notebooks", label: "Memos" },
  { key: "experiments", label: "Experiments" },
  { key: "backtests", label: "Backtests" },
  { key: "regime", label: "Regime" },
  { key: "models", label: "Models" },
];

const validTabs = new Set<LabTab>(tabs.map((tab) => tab.key));

const currency = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 2,
  style: "currency",
});

const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function ResearchLab({ initialOverview, unavailable }: ResearchLabProps) {
  const searchParams = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const initialTab =
    requestedTab && validTabs.has(requestedTab as LabTab)
      ? (requestedTab as LabTab)
      : "overview";
  const [overview, setOverview] = useState(initialOverview);
  const [activeTab, setActiveTab] = useState<LabTab>(initialTab);
  const [pipelineRun, setPipelineRun] = useState<ResearchPipelineRun | null>(null);
  const [pipelinePending, setPipelinePending] = useState(false);
  const requestedTicker = searchParams.get("ticker") ?? "";
  const requestedHorizon = searchParams.get("horizon") ?? "63";

  const highPriorityActions = useMemo(
    () => overview?.action_items.filter((item) => item.priority === "high") ?? [],
    [overview?.action_items],
  );
  const defaultTrainingTickers = useMemo(
    () => defaultTrainingUniverse(overview, requestedTicker),
    [overview, requestedTicker],
  );

  async function reloadOverview() {
    const nextOverview = await getResearchLabOverview();
    setOverview(nextOverview);
    return nextOverview;
  }

  async function handleRunPipeline(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const formData = new FormData(event.currentTarget);
    const benchmark = textValue(formData, "benchmark_ticker").toUpperCase() || "SPY";
    const tickers = parseTickerList(textValue(formData, "tickers")).filter(
      (ticker) => ticker !== benchmark,
    );
    const startDate = textValue(formData, "start_date");
    const endDate = textValue(formData, "end_date") || todayDateValue();
    const horizonDays = Number(formData.get("horizon_days") ?? 63);

    if (tickers.length === 0) {
      toast.error("Add at least one training ticker.");
      return;
    }
    if (!startDate) {
      toast.error("Choose a training start date.");
      return;
    }

    setPipelinePending(true);
    setPipelineRun(null);
    try {
      const result = await runResearchDataPipeline({
        tickers,
        benchmark_ticker: benchmark,
        start_date: startDate,
        end_date: endDate,
        horizon_days: horizonDays,
        source: "yahoo",
        train_model: formData.get("train_model") === "on",
      });
      setPipelineRun(result);
      await reloadOverview();
      if (result.model_version_id) {
        toast.success(`ML model trained for ${result.horizon_days}d horizon.`);
      } else if (result.warnings.length > 0) {
        toast.error("Pipeline finished with items to review.");
      } else {
        toast.success("Research data pipeline completed.");
      }
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Research pipeline could not run.",
      );
    } finally {
      setPipelinePending(false);
    }
  }

  if (!overview) {
    return (
      <section className="mx-auto max-w-[1200px] rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Research Lab
        </p>
        <h2 className="mt-2 text-xl font-semibold">
          {unavailable ? "Research Lab could not be loaded yet" : "Research Lab pending"}
        </h2>
        <p className="mt-2 text-sm text-zinc-500">
          {unavailable
            ? "Sign in again or refresh this page."
            : "Research data will appear here once available."}
        </p>
      </section>
    );
  }

  const summary = overview.summary;
  const metrics = [
    { label: "NAV", value: money(summary.nav) },
    { label: "Memos", value: String(summary.research_memo_count) },
    { label: "Opportunities", value: String(summary.active_opportunity_count) },
    { label: "Datasets", value: String(summary.dataset_count) },
    { label: "Feature sets", value: String(summary.feature_set_count) },
    { label: "Models", value: String(summary.model_count) },
  ];

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {summary.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              Research Lab
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              Generated {formatDateTime(overview.generated_at)}
            </p>
          </div>
          <div className="rounded-lg border border-zinc-200 px-3 py-2 text-sm text-zinc-600 dark:border-zinc-800 dark:text-zinc-300">
            {summary.warning_count} warning{summary.warning_count === 1 ? "" : "s"}
          </div>
        </div>

        <Pipeline stages={overview.pipeline} />

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-2 lg:grid-cols-6 lg:divide-x lg:divide-y-0 dark:divide-zinc-800">
          {metrics.map((metric) => (
            <div key={metric.label} className="px-5 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                {metric.label}
              </p>
              <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">
                {metric.value}
              </p>
            </div>
          ))}
        </div>
      </section>

      <TrainingRunPanel
        defaultTickers={defaultTrainingTickers}
        defaultHorizon={requestedHorizon}
        pending={pipelinePending}
        result={pipelineRun}
        onSubmit={handleRunPipeline}
        onStepComplete={() => void reloadOverview()}
      />

      <nav className="flex gap-2 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setActiveTab(tab.key)}
            className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
              activeTab === tab.key
                ? "bg-zinc-950 font-medium text-white dark:bg-zinc-100 dark:text-zinc-950"
                : "border border-zinc-200 bg-white text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {activeTab === "overview" && (
        <OverviewPanel
          actions={overview.action_items}
          checks={overview.validation_checks}
          highPriorityActions={highPriorityActions}
          notes={overview.notes}
        />
      )}
      {activeTab === "datasets" && <DatasetsPanel datasets={overview.datasets} />}
      {activeTab === "features" && <FeaturesPanel featureSets={overview.feature_sets} />}
      {activeTab === "notebooks" && <NotebooksPanel notebooks={overview.notebooks} />}
      {activeTab === "experiments" && (
        <ExperimentsPanel experiments={overview.experiments} />
      )}
      {activeTab === "backtests" && (
        <BacktestsPanel
          backtests={overview.backtests}
          defaultTickers={defaultTrainingTickers}
          defaultHorizon={requestedHorizon}
          onComplete={() => void reloadOverview()}
        />
      )}
      {activeTab === "regime" && (
        <RegimePanel active={activeTab === "regime"} onUpdated={() => void reloadOverview()} />
      )}
      {activeTab === "models" && <ModelsPanel models={overview.models} />}
    </div>
  );
}

function Pipeline({ stages }: { stages: ResearchLabOverview["pipeline"] }) {
  return (
    <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
        {stages.map((stage) => (
          <div
            key={stage.key}
            className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              {stage.label}
            </p>
            <p className="mt-1 text-xl font-semibold">{stage.count}</p>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-zinc-500">
              {stage.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

function TrainingRunPanel({
  defaultTickers,
  defaultHorizon,
  onSubmit,
  onStepComplete,
  pending,
  result,
}: {
  defaultTickers: string[];
  defaultHorizon: string;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onStepComplete?: () => void;
  pending: boolean;
  result: ResearchPipelineRun | null;
}) {
  const completedSteps =
    result?.steps.filter((step) => step.status === "completed").length ?? 0;
  const failedSteps = result?.steps.filter((step) => step.status === "failed").length ?? 0;

  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Ticker ML Layer
          </p>
          <h3 className="mt-1 text-base font-semibold">Research Data Pipeline</h3>
        </div>
        {result && (
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={failedSteps > 0 ? "needs_review" : "ready"} />
            {result.model_version_id && <StatusBadge status="validated" />}
          </div>
        )}
      </div>

      <form className="mt-5 grid gap-4 xl:grid-cols-[1fr_320px]" onSubmit={onSubmit}>
        <Field label="Training universe">
          <textarea
            name="tickers"
            rows={4}
            defaultValue={defaultTickers.join(", ")}
            placeholder="Add tickers from your research universe"
            className={inputClassName}
          />
        </Field>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1">
          <Field label="Benchmark">
            <input name="benchmark_ticker" defaultValue="SPY" className={inputClassName} />
          </Field>
          <Field label="Horizon">
            <select name="horizon_days" defaultValue={defaultHorizon} className={inputClassName}>
              <option value="21">21 days</option>
              <option value="63">63 days</option>
              <option value="126">126 days</option>
              <option value="252">252 days</option>
            </select>
          </Field>
          <Field label="Start date">
            <input
              name="start_date"
              type="date"
              defaultValue={dateYearsAgoValue(5)}
              className={inputClassName}
            />
          </Field>
          <Field label="End date">
            <input
              name="end_date"
              type="date"
              defaultValue={todayDateValue()}
              className={inputClassName}
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3 xl:col-span-2">
          <label className="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
            <input
              name="train_model"
              type="checkbox"
              defaultChecked
              className="h-4 w-4 rounded border-zinc-300 text-zinc-950"
            />
            Train predictive model after features and labels are ready
          </label>
          <div className="flex flex-wrap gap-2">
            <button type="reset" disabled={pending} className={buttonSecondaryClassName}>
              Reset
            </button>
            <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
              {pending ? "Running..." : "Run pipeline"}
            </button>
          </div>
        </div>
      </form>

      {result && (
        <div className="mt-5 rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900/50">
          <div className="grid gap-3 sm:grid-cols-4">
            <ResultMetric label="Tickers" value={String(result.tickers.length)} />
            <ResultMetric label="Completed" value={String(completedSteps)} />
            <ResultMetric label="Needs review" value={String(failedSteps)} />
            <ResultMetric
              label="Model"
              value={result.model_version_id ? "Registered" : "Not trained"}
            />
          </div>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-zinc-800">
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Step
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Status
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Rows
                  </th>
                  <th className="px-4 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
                    Message
                  </th>
                </tr>
              </thead>
              <tbody>
                {result.steps.map((step) => (
                  <tr
                    key={step.name}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                  >
                    <td className="px-4 py-3 font-medium">{formatPipelineStep(step.name)}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={step.status} />
                    </td>
                    <td className="px-4 py-3 tabular-nums text-zinc-600 dark:text-zinc-300">
                      {step.rows === null ? "-" : compact.format(step.rows)}
                    </td>
                    <td className="px-4 py-3 text-zinc-600 dark:text-zinc-300">
                      {step.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {result.warnings.length > 0 && (
            <div className="mt-4 space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {result.warnings.map((warning) => (
                <p key={warning}>{warning}</p>
              ))}
            </div>
          )}
        </div>
      )}

      <PipelineStepsPanel
        defaultTickers={defaultTickers}
        defaultHorizon={defaultHorizon}
        onComplete={onStepComplete}
      />
    </section>
  );
}

function ResultMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold">{value}</p>
    </div>
  );
}

function OverviewPanel({
  actions,
  checks,
  highPriorityActions,
  notes,
}: {
  actions: ResearchActionItem[];
  checks: ResearchValidationCheck[];
  highPriorityActions: ResearchActionItem[];
  notes: string[];
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.8fr]">
      <Panel title="Research Actions" subtitle="Next work items from the current state">
        <div className="space-y-3">
          {actions.map((item) => (
            <ActionItem key={item.key} item={item} />
          ))}
        </div>
      </Panel>

      <Panel title="Validation Checks" subtitle="Data and model readiness">
        <div className="space-y-3">
          {checks.map((check) => (
            <ValidationCheck key={check.key} check={check} />
          ))}
        </div>
      </Panel>

      <Panel title="Priority Queue" subtitle="Items that block better research output">
        {highPriorityActions.length > 0 ? (
          <div className="space-y-3">
            {highPriorityActions.map((item) => (
              <ActionItem key={item.key} item={item} compactView />
            ))}
          </div>
        ) : (
          <p className="text-sm text-zinc-500">No high-priority research blockers.</p>
        )}
      </Panel>

      <Panel title="Lab Notes">
        <div className="space-y-3">
          {notes.map((note) => (
            <p key={note} className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              {note}
            </p>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function DatasetsPanel({ datasets }: { datasets: ResearchDataset[] }) {
  return (
    <Panel title="Datasets" subtitle="Research data stores currently available">
      <DataTable
        empty="No datasets are available yet."
        headers={["Dataset", "Rows", "Instruments", "Latest", "Status", "Validation"]}
        rows={datasets.map((dataset) => [
          <div key={dataset.key}>
            <p className="font-medium">{dataset.name}</p>
            <p className="text-xs text-zinc-500">{dataset.source}</p>
          </div>,
          compact.format(dataset.row_count),
          String(dataset.instrument_count),
          dataset.latest_observation ? formatDate(dataset.latest_observation) : "-",
          <StatusBadge key={dataset.key} status={dataset.status} />,
          dataset.validation_summary,
        ])}
      />
    </Panel>
  );
}

function FeaturesPanel({ featureSets }: { featureSets: ResearchFeatureSet[] }) {
  return (
    <Panel title="Feature Sets" subtitle="Model-ready feature coverage by version">
      <DataTable
        empty="No feature snapshots are available yet."
        headers={["Version", "Snapshots", "Names", "Features", "Range", "Quality", "Status"]}
        rows={featureSets.map((featureSet) => [
          featureSet.feature_version,
          compact.format(featureSet.snapshot_count),
          String(featureSet.instrument_count),
          String(featureSet.feature_count),
          featureSet.first_as_of_date && featureSet.last_as_of_date
            ? `${formatDate(featureSet.first_as_of_date)} to ${formatDate(featureSet.last_as_of_date)}`
            : "-",
          featureSet.average_quality_score ?? "-",
          <StatusBadge key={featureSet.feature_version} status={featureSet.status} />,
        ])}
      />
      {featureSets.length > 0 && (
        <div className="mt-4 space-y-2">
          {featureSets.slice(0, 3).map((featureSet) => (
            <p
              key={featureSet.feature_version}
              className="text-sm leading-6 text-zinc-600 dark:text-zinc-300"
            >
              {featureSet.feature_version}: {featureSet.notes}
            </p>
          ))}
        </div>
      )}
    </Panel>
  );
}

function NotebooksPanel({ notebooks }: { notebooks: ResearchNotebook[] }) {
  return (
    <Panel title="Research Memos" subtitle="User-owned analyst work from Ticker Analyst">
      <DataTable
        empty="No research memos are available yet."
        headers={["Memo", "Date", "Class", "Status", "Summary"]}
        rows={notebooks.map((notebook) => [
          <div key={notebook.id}>
            <p className="font-medium">{notebook.title}</p>
            <p className="text-xs text-zinc-500">{notebook.ticker}</p>
          </div>,
          formatDate(notebook.memo_date),
          formatLabel(notebook.classification),
          <StatusBadge key={notebook.id} status={notebook.status} />,
          <p key={`${notebook.id}-summary`} className="line-clamp-2 max-w-xl">
            {notebook.summary}
          </p>,
        ])}
      />
    </Panel>
  );
}

function ExperimentsPanel({
  experiments,
}: {
  experiments: ResearchExperiment[];
}) {
  return (
    <Panel title="Experiments" subtitle="Model versions and research trials">
      <DataTable
        empty="No experiments are registered yet."
        headers={["Experiment", "Type", "Metric", "Feature set", "Status", "Created"]}
        rows={experiments.map((experiment) => [
          <div key={experiment.id}>
            <p className="font-medium">{experiment.name}</p>
            <p className="line-clamp-1 text-xs text-zinc-500">{experiment.hypothesis}</p>
          </div>,
          formatLabel(experiment.experiment_type),
          experiment.validation_metric && experiment.validation_value
            ? `${experiment.validation_metric}: ${experiment.validation_value}`
            : "-",
          experiment.feature_version ?? "-",
          <StatusBadge key={experiment.id} status={experiment.status} />,
          formatDate(experiment.created_at),
        ])}
      />
    </Panel>
  );
}

function ModelsPanel({ models }: { models: ResearchModel[] }) {
  return (
    <Panel title="Model Registry" subtitle="Predictive models available to the analyst">
      <DataTable
        empty="No trained models are registered yet."
        headers={["Model", "Horizon", "Rows", "Accuracy", "R2", "Status"]}
        rows={models.map((model) => [
          <div key={model.model_version_id}>
            <p className="font-medium">{model.model_name}</p>
            <p className="text-xs text-zinc-500">{model.model_version}</p>
          </div>,
          model.horizon_days ? `${model.horizon_days}d` : "-",
          `${model.training_rows ?? 0} / ${model.validation_rows ?? 0}`,
          model.validation_directional_accuracy
            ? `${Number(model.validation_directional_accuracy).toFixed(2)}%`
            : "-",
          model.validation_r2 ?? "-",
          <StatusBadge key={model.model_version_id} status={model.status} />,
        ])}
      />
    </Panel>
  );
}

function ActionItem({
  compactView,
  item,
}: {
  compactView?: boolean;
  item: ResearchActionItem;
}) {
  const content = (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 transition hover:border-zinc-200 dark:border-zinc-900 dark:bg-zinc-900/50 dark:hover:border-zinc-700">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium">{item.label}</p>
          <p className="mt-1 text-xs text-zinc-500">{item.owner_area}</p>
        </div>
        <PriorityBadge priority={item.priority} />
      </div>
      {!compactView && (
        <p className="mt-3 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {item.detail}
        </p>
      )}
    </div>
  );

  if (!item.action_path) return content;
  return <Link href={item.action_path}>{content}</Link>;
}

function ValidationCheck({ check }: { check: ResearchValidationCheck }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm font-medium">{check.label}</p>
        <StatusBadge status={check.status} />
      </div>
      <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
        {check.detail}
      </p>
    </div>
  );
}

function Panel({
  children,
  subtitle,
  title,
}: {
  children: ReactNode;
  subtitle?: string;
  title: string;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function DataTable({
  empty,
  headers,
  rows,
}: {
  empty: string;
  headers: string[];
  rows: ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800">
            {headers.map((header) => (
              <th
                key={header}
                className="whitespace-nowrap px-5 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
            >
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="px-5 py-3 align-middle text-zinc-700 dark:text-zinc-300"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td
                colSpan={headers.length}
                className="px-5 py-10 text-center text-sm text-zinc-500"
              >
                {empty}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles = statusStyle(status);
  return (
    <span className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${styles}`}>
      {formatLabel(status)}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${
        priority === "high"
          ? "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
          : "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300"
      }`}
    >
      {formatLabel(priority)}
    </span>
  );
}

function statusStyle(status: string) {
  if (["completed", "passed", "validated", "ready", "candidate"].includes(status)) {
    return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
  }
  if (["warning", "needs_review", "blocked"].includes(status)) {
    return "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
  }
  if (["failed", "archived"].includes(status)) {
    return "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300";
  }
  return "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300";
}

function defaultTrainingUniverse(
  overview: ResearchLabOverview | null,
  requestedTicker: string,
) {
  const requestedTickers = parseTickerList(requestedTicker);
  const memoTickers =
    overview?.notebooks.map((notebook) => notebook.ticker.toUpperCase()) ?? [];
  return uniqueTickers([...requestedTickers, ...memoTickers])
    .filter((ticker) => ticker !== "SPY")
    .slice(0, 20);
}

function formatPipelineStep(value: string) {
  return value
    .replace("price_backfill:", "Price backfill / ")
    .replace("labels:", "Labels / ")
    .replace("price_features", "Price features")
    .replace("predictive_model", "Predictive model");
}

function textValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function Field({
  children,
  label,
}: {
  children: ReactNode;
  label: string;
}) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      {label}
      {children}
    </label>
  );
}

function money(value: string) {
  return currency.format(Number(value));
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
