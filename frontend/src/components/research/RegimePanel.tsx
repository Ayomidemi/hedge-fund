"use client";

import { useEffect, useState, type ReactNode } from "react";
import type { FormEvent } from "react";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { fitRegimeModel, getLatestRegimeModel, type RegimeModel } from "@/lib/api";
import type { TickerMarket } from "@/lib/ticker-prefill-form";
import { LabPanel, StatusBadge, formatDate, formatLabel, pct } from "./research-lab-ui";

type RegimePanelProps = {
  active: boolean;
  onUpdated?: () => void;
};

export function RegimePanel({ active, onUpdated }: RegimePanelProps) {
  const [regime, setRegime] = useState<RegimeModel | null>(null);
  const [loading, setLoading] = useState(false);
  const [fitting, setFitting] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [fitMarket, setFitMarket] = useState<TickerMarket>("US");
  const [fitTicker, setFitTicker] = useState("SPY");

  useEffect(() => {
    if (!active) return;
    void loadRegime();
  }, [active]);

  async function loadRegime() {
    setLoading(true);
    setUnavailable(false);
    try {
      const next = await getLatestRegimeModel();
      setRegime(next);
    } catch {
      setRegime(null);
      setUnavailable(true);
    } finally {
      setLoading(false);
    }
  }

  async function handleFit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const ticker = String(formData.get("ticker") ?? "SPY").toUpperCase();
    const stateCount = Number(formData.get("state_count") ?? 4);
    const lookbackDays = Number(formData.get("lookback_days") ?? 756);

    setFitting(true);
    try {
      const next = await fitRegimeModel({
        ticker,
        state_count: stateCount,
        lookback_days: lookbackDays,
        source: "yahoo",
      });
      setRegime(next);
      setUnavailable(false);
      onUpdated?.();
      toast.success(`Regime model fit for ${next.ticker}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Regime model could not be fit.");
    } finally {
      setFitting(false);
    }
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.9fr]">
      <LabPanel
        title="Market regime model"
        subtitle="HMM classification used by the Macro Regime pod and strategy overlays"
      >
        {loading ? (
          <p className="text-sm text-zinc-500">Loading regime model…</p>
        ) : regime ? (
          <div className="space-y-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-2xl font-semibold capitalize tracking-tight">
                  {formatLabel(regime.current_regime)}
                </p>
                <p className="mt-1 text-sm text-zinc-500">
                  {regime.ticker} · as of {formatDate(regime.as_of_date)} ·{" "}
                  {pct(regime.confidence_score)} confidence
                </p>
              </div>
              <StatusBadge status="validated" />
            </div>

            <dl className="grid gap-3 sm:grid-cols-2">
              <Metric label="Model" value={`${regime.model_name} ${regime.model_version}`} />
              <Metric label="States" value={String(regime.state_probabilities.length)} />
            </dl>

            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                State probabilities
              </p>
              <div className="mt-3 space-y-2">
                {regime.state_probabilities.map((state) => (
                  <div
                    key={state.state_id}
                    className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2 dark:border-zinc-900 dark:bg-zinc-900/50"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-medium capitalize">{formatLabel(state.label)}</p>
                      <p className="text-sm tabular-nums text-zinc-600 dark:text-zinc-300">
                        {pct(state.probability)}
                      </p>
                    </div>
                    <p className="mt-1 text-xs text-zinc-500">
                      Mean return {pct(state.mean_return_pct)} · Vol {pct(state.volatility_pct)} ·{" "}
                      {state.observation_count} obs
                    </p>
                  </div>
                ))}
              </div>
            </div>

            {regime.warnings.length > 0 && (
              <div className="space-y-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
                {regime.warnings.map((warning) => (
                  <p key={warning}>{warning}</p>
                ))}
              </div>
            )}

            <button
              type="button"
              onClick={() => void loadRegime()}
              disabled={loading || fitting}
              className={buttonSecondaryClassName}
            >
              Refresh
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              {unavailable
                ? "No regime model has been fit yet. Run the fit form to classify the current market state."
                : "Regime model is not available."}
            </p>
            <p className="text-sm text-zinc-500">
              Price history for the benchmark (typically SPY) must exist before fitting. Use the
              research data pipeline or backfill prices first.
            </p>
          </div>
        )}
      </LabPanel>

      <LabPanel title="Fit regime model" subtitle="Cluster return and volatility observations">
        <form className="space-y-4" onSubmit={handleFit}>
          <TickerSelector
            fetchDetailsOnSelect={false}
            market={fitMarket}
            marketName="ticker_market"
            onMarketChange={setFitMarket}
            onTickerChange={setFitTicker}
            placeholder="SPY"
            tickerLabel="Benchmark ticker"
            tickerName="ticker"
            value={fitTicker}
          />
          <Field label="State count">
            <select name="state_count" defaultValue="4" className={inputClassName}>
              <option value="3">3 states</option>
              <option value="4">4 states</option>
              <option value="5">5 states</option>
            </select>
          </Field>
          <Field label="Lookback days">
            <input
              name="lookback_days"
              type="number"
              min={60}
              max={5000}
              defaultValue={756}
              className={inputClassName}
            />
          </Field>
          <button type="submit" disabled={fitting} className={buttonPrimaryClassName}>
            {fitting ? "Fitting…" : "Fit HMM regime model"}
          </button>
        </form>
      </LabPanel>
    </div>
  );
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
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 px-3 py-2 dark:border-zinc-900 dark:bg-zinc-900/50">
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="mt-1 text-sm font-medium">{value}</dd>
    </div>
  );
}
