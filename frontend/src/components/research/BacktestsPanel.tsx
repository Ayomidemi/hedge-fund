"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createFactorBacktest,
  type BacktestRun,
  type ResearchBacktest,
} from "@/lib/api";
import {
  LabPanel,
  StatusBadge,
  formatDate,
  formatLabel,
  parseTickerList,
  pct,
} from "./research-lab-ui";

const compact = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
  notation: "compact",
});

type BacktestsPanelProps = {
  backtests: ResearchBacktest[];
  defaultTickers: string[];
  defaultHorizon: string;
  onComplete?: () => void;
};

export function BacktestsPanel({
  backtests,
  defaultTickers,
  defaultHorizon,
  onComplete,
}: BacktestsPanelProps) {
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState<BacktestRun | null>(null);

  async function handleRun(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const tickers = parseTickerList(String(formData.get("tickers") ?? ""));
    const benchmark = String(formData.get("benchmark_ticker") ?? "SPY").toUpperCase();
    const horizonDays = Number(formData.get("horizon_days") ?? 63);
    const topN = Number(formData.get("top_n") ?? 5);
    const minNames = Number(formData.get("min_names_per_period") ?? 3);
    const costBps = String(formData.get("transaction_cost_bps") ?? "10");

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
      });
      setResult(next);
      onComplete?.();
      toast.success("Factor backtest completed.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Backtest could not run.");
    } finally {
      setPending(false);
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
        subtitle="Walk-forward rank on feature snapshots with configurable costs and top-N selection"
      >
        <form className="grid gap-4 xl:grid-cols-[1fr_280px]" onSubmit={handleRun}>
          <label className="block space-y-1.5">
            <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              Universe
            </span>
            <textarea
              name="tickers"
              rows={4}
              defaultValue={defaultTickers.join(", ")}
              className={inputClassName}
              placeholder="Tickers with feature snapshots and labels"
            />
          </label>

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
              <input
                name="transaction_cost_bps"
                defaultValue="10"
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

        {result && (
          <div className="mt-5 space-y-4 rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900/50">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{result.name}</p>
                <p className="mt-1 text-sm text-zinc-500">
                  {result.start_date && result.end_date
                    ? `${formatDate(result.start_date)} to ${formatDate(result.end_date)}`
                    : "—"}{" "}
                  · {result.rebalance_count} rebalances
                </p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <Metric label="Cumulative return" value={pct(result.cumulative_return_pct)} />
              <Metric label="Sharpe" value={Number(result.sharpe_ratio).toFixed(2)} />
              <Metric label="Max drawdown" value={pct(result.max_drawdown_pct)} />
              <Metric label="Hit rate" value={pct(result.hit_rate_pct)} />
              <Metric label="Annualized return" value={pct(result.annualized_return_pct)} />
              <Metric label="Volatility" value={pct(result.annualized_volatility_pct)} />
              <Metric label="Alpha vs benchmark" value={result.alpha_pct ? pct(result.alpha_pct) : "—"} />
              <Metric label="Avg turnover" value={pct(result.turnover_pct)} />
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-zinc-800">
                    <Th>As of</Th>
                    <Th>Selected</Th>
                    <Th>Strategy</Th>
                    <Th>Benchmark</Th>
                    <Th>Alpha</Th>
                    <Th>Turnover</Th>
                  </tr>
                </thead>
                <tbody>
                  {result.periods.slice(-12).map((period) => (
                    <tr
                      key={period.as_of_date}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
                    >
                      <Td>{formatDate(period.as_of_date)}</Td>
                      <Td>{period.selected_tickers.join(", ")}</Td>
                      <Td>{pct(period.strategy_return_pct)}</Td>
                      <Td>
                        {period.benchmark_return_pct ? pct(period.benchmark_return_pct) : "—"}
                      </Td>
                      <Td>{period.alpha_pct ? pct(period.alpha_pct) : "—"}</Td>
                      <Td>{pct(period.turnover_pct)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.periods.length > 12 && (
              <p className="text-xs text-zinc-500">
                Showing last 12 of {compact.format(result.periods.length)} rebalance periods.
              </p>
            )}

            {result.warnings.length > 0 && (
              <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {result.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </LabPanel>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
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

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return <td className="px-3 py-2 text-zinc-700 dark:text-zinc-300">{children}</td>;
}
