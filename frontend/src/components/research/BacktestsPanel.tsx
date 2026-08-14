"use client";

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createFactorBacktest,
  getSavedBacktest,
  getSavedBacktests,
  type BacktestPeriod,
  type ResearchBacktest,
  type SavedBacktestRun,
} from "@/lib/api";
import {
  LabPanel,
  StatusBadge,
  formatDate,
  formatDateTime,
  parseTickerList,
  pct,
} from "./research-lab-ui";

const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

type DisplayRun = {
  name: string;
  start_date: string | null;
  end_date: string | null;
  rebalance_count: number;
  cumulative_return_pct: string;
  benchmark_return_pct: string | null;
  alpha_pct: string | null;
  annualized_return_pct: string;
  annualized_volatility_pct: string;
  sharpe_ratio: string;
  max_drawdown_pct: string;
  hit_rate_pct: string;
  turnover_pct: string;
  regime_filter_applied: boolean;
  skipped_by_regime: number;
  periods: BacktestPeriod[];
  warnings: string[];
};

type BacktestsPanelProps = {
  backtests: ResearchBacktest[];
  defaultTickers: string[];
  defaultHorizon: string;
  hasRegimeModel: boolean;
  onComplete?: () => void;
};

export function BacktestsPanel({
  backtests,
  defaultTickers,
  defaultHorizon,
  hasRegimeModel,
  onComplete,
}: BacktestsPanelProps) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<DisplayRun | null>(null);
  const [history, setHistory] = useState<SavedBacktestRun[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [loadingRunId, setLoadingRunId] = useState<string | null>(null);

  useEffect(() => {
    void loadHistory();
  }, []);

  async function loadHistory() {
    setHistoryLoading(true);
    try {
      setHistory(await getSavedBacktests());
    } catch {
      setHistory([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const tickers = parseTickerList(String(formData.get("tickers") ?? ""));
    const benchmark = String(formData.get("benchmark_ticker") ?? "SPY").toUpperCase();
    const horizonDays = Number(formData.get("horizon_days") ?? 63);
    const topN = Number(formData.get("top_n") ?? 5);
    const minNames = Number(formData.get("min_names_per_period") ?? 3);
    const costBps = String(formData.get("transaction_cost_bps") ?? "10");
    const slippageBps = String(formData.get("slippage_bps") ?? "5");
    const executionLagDays = Number(formData.get("execution_lag_days") ?? 1);
    const regimeFilter = formData.get("regime_filter") === "on";

    if (tickers.length === 0) {
      toast.error("Add at least one ticker to backtest.");
      return;
    }

    setPending(true);
    setResult(null);
    try {
      const next = await createFactorBacktest({
        tickers,
        benchmark_ticker: benchmark,
        horizon_days: horizonDays,
        top_n: topN,
        min_names_per_period: minNames,
        transaction_cost_bps: costBps,
        slippage_bps: slippageBps,
        execution_lag_days: executionLagDays,
        regime_filter: regimeFilter,
      });
      setResult(next);
      await loadHistory();
      onComplete?.();
      toast.success(
        next.regime_filter_applied
          ? "Regime-filtered backtest completed and saved."
          : "Factor backtest completed and saved.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Backtest could not run.");
    } finally {
      setPending(false);
    }
  }

  async function openSavedRun(runId: string) {
    setLoadingRunId(runId);
    try {
      const run = await getSavedBacktest(runId);
      setResult(run);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Saved backtest could not load.",
      );
    } finally {
      setLoadingRunId(null);
    }
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 xl:grid-cols-2">
        {backtests.map((backtest) => (
          <div
            key={backtest.id}
            className="rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900/50"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{backtest.name}</p>
                <p className="mt-1 text-xs text-zinc-500">
                  {backtest.benchmark ?? "No benchmark"} / {backtest.cost_model}
                </p>
              </div>
              <StatusBadge status={backtest.status} />
            </div>
            <p className="mt-4 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              {backtest.strategy}
            </p>
            <p className="mt-3 text-sm leading-6 text-zinc-500">{backtest.notes}</p>
          </div>
        ))}
      </div>

      <LabPanel
        title="Run factor ranker backtest"
        subtitle="Walk-forward rank on feature snapshots with transaction costs, slippage, execution lag, and optional regime filtering"
      >
        <form className="grid gap-4 xl:grid-cols-[1fr_300px]" onSubmit={handleRun}>
          <div className="space-y-4">
            <Field label="Universe">
              <textarea
                name="tickers"
                rows={4}
                defaultValue={defaultTickers.join(", ")}
                className={inputClassName}
                placeholder="Tickers with feature snapshots and labels"
              />
            </Field>
            <label className="flex items-start gap-2.5 rounded-lg border border-zinc-100 bg-zinc-50 p-3 text-sm dark:border-zinc-900 dark:bg-zinc-900/50">
              <input
                name="regime_filter"
                type="checkbox"
                disabled={!hasRegimeModel}
                className="mt-0.5 h-4 w-4 rounded border-zinc-300 text-zinc-950"
              />
              <span>
                <span className="font-medium text-zinc-800 dark:text-zinc-200">
                  Regime filter (ML)
                </span>
                <span className="mt-0.5 block text-zinc-500">
                  {hasRegimeModel
                    ? "Exit to cash when the HMM model classifies the market as stressed."
                    : "Fit the HMM regime model on the Regime tab to enable this."}
                </span>
              </span>
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2">
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
            <Field label="Top N">
              <input name="top_n" type="number" min={1} max={50} defaultValue={5} className={inputClassName} />
            </Field>
            <Field label="Min names / period">
              <input
                name="min_names_per_period"
                type="number"
                min={1}
                max={100}
                defaultValue={3}
                className={inputClassName}
              />
            </Field>
            <Field label="Cost (bps)">
              <input name="transaction_cost_bps" defaultValue="10" className={inputClassName} />
            </Field>
            <Field label="Slippage (bps)">
              <input name="slippage_bps" defaultValue="5" className={inputClassName} />
            </Field>
            <Field label="Execution lag (days)">
              <input
                name="execution_lag_days"
                type="number"
                min={0}
                max={10}
                defaultValue={1}
                className={inputClassName}
              />
            </Field>
          </div>

          <div className="flex justify-end xl:col-span-2">
            <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
              {pending ? "Running…" : "Run backtest"}
            </button>
          </div>
        </form>

        {result && <RunResult run={result} />}
      </LabPanel>

      <LabPanel
        title="Saved backtest history"
        subtitle="Every run is stored with its parameters and periods for reproducibility"
      >
        {historyLoading ? (
          <p className="text-sm text-zinc-500">Loading history…</p>
        ) : history.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No saved runs yet. Runs are saved automatically when you execute a backtest.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 dark:border-zinc-800">
                  <Th>Run</Th>
                  <Th>When</Th>
                  <Th>Return</Th>
                  <Th>Sharpe</Th>
                  <Th>Drawdown</Th>
                  <Th>Hit rate</Th>
                  <Th>Regime</Th>
                  <Th> </Th>
                </tr>
              </thead>
              <tbody>
                {history.map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                  >
                    <Td>
                      <p className="font-medium">{run.name}</p>
                      <p className="text-xs text-zinc-500">
                        {run.rebalance_count} rebalances · {run.horizon_days}d
                      </p>
                    </Td>
                    <Td>{formatDateTime(run.created_at)}</Td>
                    <Td>
                      <ReturnValue value={run.cumulative_return_pct} />
                    </Td>
                    <Td>{Number(run.sharpe_ratio).toFixed(2)}</Td>
                    <Td>{pct(run.max_drawdown_pct)}</Td>
                    <Td>{pct(run.hit_rate_pct)}</Td>
                    <Td>
                      {run.regime_filter_applied ? `On (${run.skipped_by_regime} skipped)` : "Off"}
                    </Td>
                    <Td>
                      <button
                        type="button"
                        onClick={() => void openSavedRun(run.id)}
                        disabled={loadingRunId !== null}
                        className={buttonSecondaryClassName}
                      >
                        {loadingRunId === run.id ? "Loading…" : "View"}
                      </button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </LabPanel>
    </div>
  );
}

function RunResult({ run }: { run: DisplayRun }) {
  return (
    <div className="mt-5 space-y-4 rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900/50">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium">{run.name}</p>
          <p className="mt-1 text-sm text-zinc-500">
            {run.start_date && run.end_date
              ? `${formatDate(run.start_date)} to ${formatDate(run.end_date)}`
              : "—"}{" "}
            · {run.rebalance_count} rebalances
            {run.regime_filter_applied &&
              ` · regime filter on (${run.skipped_by_regime} period(s) in cash)`}
          </p>
        </div>
      </div>

      <EquityCurve periods={run.periods} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Metric label="Cumulative return" value={pct(run.cumulative_return_pct)} />
        <Metric label="Sharpe" value={Number(run.sharpe_ratio).toFixed(2)} />
        <Metric label="Max drawdown" value={pct(run.max_drawdown_pct)} />
        <Metric label="Hit rate" value={pct(run.hit_rate_pct)} />
        <Metric label="Annualized return" value={pct(run.annualized_return_pct)} />
        <Metric label="Volatility" value={pct(run.annualized_volatility_pct)} />
        <Metric label="Alpha vs benchmark" value={run.alpha_pct ? pct(run.alpha_pct) : "—"} />
        <Metric label="Avg turnover" value={pct(run.turnover_pct)} />
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>As of</Th>
              <Th>Selected</Th>
              <Th>Strategy</Th>
              <Th>Benchmark</Th>
              <Th>Alpha</Th>
              <Th>Turnover</Th>
              <Th>Regime</Th>
            </tr>
          </thead>
          <tbody>
            {run.periods.slice(-12).map((period) => (
              <tr
                key={period.as_of_date}
                className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
              >
                <Td>{formatDate(period.as_of_date)}</Td>
                <Td>
                  {period.skipped_by_regime ? (
                    <span className="text-zinc-500">Cash (regime)</span>
                  ) : (
                    period.selected_tickers.join(", ")
                  )}
                </Td>
                <Td>
                  <ReturnValue value={period.strategy_return_pct} />
                </Td>
                <Td>{period.benchmark_return_pct ? pct(period.benchmark_return_pct) : "—"}</Td>
                <Td>{period.alpha_pct ? pct(period.alpha_pct) : "—"}</Td>
                <Td>{pct(period.turnover_pct)}</Td>
                <Td>{period.regime ?? "—"}</Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {run.periods.length > 12 && (
        <p className="text-xs text-zinc-500">
          Showing last 12 of {compact.format(run.periods.length)} rebalance periods.
        </p>
      )}

      {run.warnings.length > 0 && (
        <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          {run.warnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      )}
    </div>
  );
}

function EquityCurve({ periods }: { periods: BacktestPeriod[] }) {
  if (periods.length < 2) return null;

  const width = 720;
  const height = 180;
  const padding = 8;

  const strategySeries: number[] = [];
  const benchmarkSeries: number[] = [];
  let strategyEquity = 1;
  let benchmarkEquity = 1;
  let hasFullBenchmark = true;

  for (const period of periods) {
    strategyEquity *= 1 + Number(period.strategy_return_pct) / 100;
    strategySeries.push(strategyEquity);
    if (period.benchmark_return_pct === null) {
      hasFullBenchmark = false;
    } else {
      benchmarkEquity *= 1 + Number(period.benchmark_return_pct) / 100;
    }
    benchmarkSeries.push(benchmarkEquity);
  }

  const allValues = hasFullBenchmark
    ? [...strategySeries, ...benchmarkSeries, 1]
    : [...strategySeries, 1];
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const range = max - min || 1;

  const toPoints = (series: number[]) =>
    series
      .map((value, index) => {
        const x = padding + (index / (series.length - 1)) * (width - padding * 2);
        const y = height - padding - ((value - min) / range) * (height - padding * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  const baselineY =
    height - padding - ((1 - min) / range) * (height - padding * 2);

  return (
    <div>
      <div className="flex items-center gap-4 text-xs text-zinc-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-0.5 w-4 rounded bg-emerald-600" /> Strategy
        </span>
        {hasFullBenchmark && (
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-4 rounded bg-zinc-400" /> Benchmark
          </span>
        )}
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-2 h-44 w-full rounded-lg border border-zinc-100 bg-white dark:border-zinc-900 dark:bg-zinc-950"
        role="img"
        aria-label="Equity curve of strategy versus benchmark"
      >
        <line
          x1={padding}
          x2={width - padding}
          y1={baselineY}
          y2={baselineY}
          className="stroke-zinc-200 dark:stroke-zinc-800"
          strokeDasharray="4 4"
        />
        {hasFullBenchmark && (
          <polyline
            points={toPoints(benchmarkSeries)}
            fill="none"
            className="stroke-zinc-400"
            strokeWidth="1.5"
          />
        )}
        <polyline
          points={toPoints(strategySeries)}
          fill="none"
          className="stroke-emerald-600"
          strokeWidth="2"
        />
      </svg>
    </div>
  );
}

function ReturnValue({ value }: { value: string }) {
  const numeric = Number(value);
  const tone =
    numeric > 0
      ? "text-emerald-700 dark:text-emerald-400"
      : numeric < 0
        ? "text-rose-700 dark:text-rose-400"
        : "text-zinc-600 dark:text-zinc-300";
  return <span className={`tabular-nums ${tone}`}>{pct(value)}</span>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</span>
      {children}
    </label>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Th({ children }: { children: ReactNode }) {
  return (
    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
      {children}
    </th>
  );
}

function Td({ children }: { children: ReactNode }) {
  return <td className="px-3 py-2 align-middle text-zinc-700 dark:text-zinc-300">{children}</td>;
}
