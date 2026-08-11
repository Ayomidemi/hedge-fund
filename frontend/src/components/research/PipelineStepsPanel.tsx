"use client";

import { useState } from "react";
import { toast } from "@/components/ui/ToastProvider";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import {
  backfillYahooPrices,
  buildPriceFeatures,
  generateTrainingLabels,
  trainPredictiveModel,
} from "@/lib/api";
import { dateYearsAgoValue, formatLabel, todayDateValue } from "./research-lab-ui";

type PipelineStepsPanelProps = {
  defaultTickers: string[];
  defaultHorizon: string;
  onComplete?: () => void;
};

type StepResult = {
  step: string;
  message: string;
};

export function PipelineStepsPanel({
  defaultTickers,
  defaultHorizon,
  onComplete,
}: PipelineStepsPanelProps) {
  const [pendingStep, setPendingStep] = useState<string | null>(null);
  const [results, setResults] = useState<StepResult[]>([]);

  const benchmark = "SPY";
  const startDate = dateYearsAgoValue(5);
  const endDate = todayDateValue();
  const horizonDays = Number(defaultHorizon) || 63;

  async function runStep(step: string, action: () => Promise<string>) {
    if (defaultTickers.length === 0) {
      toast.error("Add tickers to the training universe first.");
      return;
    }

    setPendingStep(step);
    try {
      const message = await action();
      setResults((current) => [{ step, message }, ...current].slice(0, 8));
      onComplete?.();
      toast.success(formatLabel(step) + " completed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `${formatLabel(step)} failed.`);
    } finally {
      setPendingStep(null);
    }
  }

  async function runBackfill() {
    let totalSaved = 0;
    for (const ticker of defaultTickers) {
      const result = await backfillYahooPrices({
        ticker,
        start_date: startDate,
        end_date: endDate,
      });
      totalSaved += result.rows_saved;
    }
    return `Saved ${totalSaved.toLocaleString()} price bars across ${defaultTickers.length} tickers.`;
  }

  async function runLabels() {
    let totalLabels = 0;
    for (const ticker of defaultTickers) {
      const result = await generateTrainingLabels({
        ticker,
        benchmark_ticker: benchmark,
        horizons: [21, horizonDays, 126],
      });
      totalLabels += result.labels_generated;
    }
    return `Generated ${totalLabels.toLocaleString()} labels across ${defaultTickers.length} tickers.`;
  }

  async function runFeatures() {
    const result = await buildPriceFeatures({ tickers: defaultTickers });
    return `Saved ${result.snapshots_saved.toLocaleString()} feature snapshots.`;
  }

  async function runTrain() {
    const result = await trainPredictiveModel({
      tickers: defaultTickers,
      benchmark_ticker: benchmark,
      horizon_days: horizonDays,
    });
    const accuracy = result.metrics.validation_directional_accuracy;
    return `Registered ${result.model_version} (${result.training_rows} train / ${result.validation_rows} validation rows${
      accuracy !== undefined ? `, ${Number(accuracy).toFixed(1)}% directional accuracy` : ""
    }).`;
  }

  const steps = [
    { key: "price_backfill", label: "Backfill prices", run: runBackfill },
    { key: "generate_labels", label: "Generate labels", run: runLabels },
    { key: "build_features", label: "Build features", run: runFeatures },
    { key: "train_model", label: "Train model", run: runTrain },
  ] as const;

  return (
    <details className="mt-5 rounded-lg border border-zinc-100 bg-zinc-50 dark:border-zinc-900 dark:bg-zinc-900/50">
      <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-zinc-700 dark:text-zinc-300">
        Run individual pipeline steps
      </summary>
      <div className="space-y-4 border-t border-zinc-100 px-4 py-4 dark:border-zinc-900">
        <p className="text-sm text-zinc-500">
          Use these when a full pipeline run partially fails, or when you only need to refresh one
          layer. Steps use the training universe above ({defaultTickers.length} tickers,{" "}
          {horizonDays}d horizon).
        </p>
        <div className="flex flex-wrap gap-2">
          {steps.map((step) => (
            <button
              key={step.key}
              type="button"
              disabled={pendingStep !== null}
              onClick={() => void runStep(step.key, step.run)}
              className={buttonSecondaryClassName}
            >
              {pendingStep === step.key ? "Running…" : step.label}
            </button>
          ))}
        </div>
        {results.length > 0 && (
          <ul className="space-y-2 text-sm text-zinc-600 dark:text-zinc-300">
            {results.map((result) => (
              <li key={`${result.step}-${result.message}`}>
                <span className="font-medium">{formatLabel(result.step)}:</span> {result.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
