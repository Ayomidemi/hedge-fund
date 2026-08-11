"use client";

import { FormEvent, useState } from "react";
import { TickerCombobox } from "@/components/ticker/TickerCombobox";
import { HorizontalBarPlot } from "@/components/ui/plots";
import {
  captureRiskSnapshot,
  createCustomStressTest,
  createPreTradeRiskCheck,
  getRiskCentreOverview,
  type PreTradeRiskInput,
  type PreTradeRiskCheck,
  type RiskCentreOverview,
  type RiskMeasurement,
  type StressTestResult,
} from "@/lib/api";

type RiskCentreProps = {
  initialOverview: RiskCentreOverview | null;
  unavailable: boolean;
};

type RiskTab = "overview" | "limits" | "stress" | "pretrade";

const tabs: { key: RiskTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "limits", label: "Limits" },
  { key: "stress", label: "Stress Tests" },
  { key: "pretrade", label: "Pre-Trade" },
];

const currency = new Intl.NumberFormat("en-US", {
  currency: "USD",
  maximumFractionDigits: 2,
  style: "currency",
});

export function RiskCentre({ initialOverview, unavailable }: RiskCentreProps) {
  const [overview, setOverview] = useState(initialOverview);
  const [activeTab, setActiveTab] = useState<RiskTab>("overview");
  const [pending, setPending] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(
    unavailable ? "Risk overview could not be loaded yet." : null,
  );
  const [customStress, setCustomStress] = useState<StressTestResult | null>(null);
  const [preTrade, setPreTrade] = useState<PreTradeRiskCheck | null>(null);

  async function refreshOverview() {
    setPending("refresh");
    setMessage(null);
    try {
      setOverview(await getRiskCentreOverview());
    } catch {
      setMessage("Risk overview could not be loaded.");
    } finally {
      setPending(null);
    }
  }

  async function handleCapture() {
    setPending("capture");
    setMessage(null);
    try {
      const result = await captureRiskSnapshot();
      setMessage(`Snapshot captured with ${result.measurement_count} checks.`);
      await refreshOverview();
    } catch {
      setMessage("Snapshot could not be captured.");
    } finally {
      setPending(null);
    }
  }

  async function handleStressSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const ticker = textValue(formData, "ticker");
    const tickerShock = textValue(formData, "ticker_shock_pct");
    const sector = textValue(formData, "sector");
    const sectorShock = textValue(formData, "sector_shock_pct");

    setPending("stress");
    setMessage(null);
    try {
      const result = await createCustomStressTest({
        name: textValue(formData, "name") || "Custom scenario",
        market_shock_pct: textValue(formData, "market_shock_pct") || "0",
        cash_shock_pct: textValue(formData, "cash_shock_pct") || "0",
        ticker_shocks_pct: ticker && tickerShock ? { [ticker.toUpperCase()]: tickerShock } : {},
        sector_shocks_pct: sector && sectorShock ? { [sector]: sectorShock } : {},
        notes: textValue(formData, "notes") || undefined,
      });
      setCustomStress(result);
    } catch {
      setMessage("Custom stress test failed.");
    } finally {
      setPending(null);
    }
  }

  async function handlePreTradeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const ticker = textValue(formData, "ticker");
    const name = textValue(formData, "name") || ticker;

    setPending("pretrade");
    setMessage(null);
    try {
      const result = await createPreTradeRiskCheck({
        instrument: {
          ticker,
          name,
          asset_class: assetClassValue(formData),
          exchange: textValue(formData, "exchange") || undefined,
          currency: textValue(formData, "currency") || "USD",
          sector: textValue(formData, "sector") || undefined,
          industry: textValue(formData, "industry") || undefined,
        },
        side: sideValue(formData),
        quantity: textValue(formData, "quantity"),
        price: textValue(formData, "price"),
        fees: textValue(formData, "fees") || "0",
        rationale: textValue(formData, "rationale") || undefined,
      });
      setPreTrade(result);
    } catch {
      setMessage("Pre-trade check failed.");
    } finally {
      setPending(null);
    }
  }

  if (!overview) {
    return (
      <section className="mx-auto max-w-[1200px] rounded-xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Risk Centre
        </p>
        <h2 className="mt-2 text-xl font-semibold">Risk engine pending</h2>
        <p className="mt-2 text-sm text-zinc-500">
          {message ?? "Portfolio state is not available yet."}
        </p>
        <button
          type="button"
          onClick={refreshOverview}
          className={`${primaryButtonClass} mt-4`}
        >
          Retry
        </button>
      </section>
    );
  }

  const snapshot = overview.snapshot;
  const failedChecks = overview.measurements.filter((check) => !check.passed);

  return (
    <div className="mx-auto max-w-[1560px] space-y-5">
      <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Central Risk Office
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-normal">
              {snapshot.risk_level_label}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {snapshot.portfolio_name} · {snapshot.as_of_date}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={refreshOverview}
              disabled={pending !== null}
              className={secondaryButtonClass}
            >
              {pending === "refresh" ? "Refreshing..." : "Refresh"}
            </button>
            <button
              type="button"
              onClick={handleCapture}
              disabled={pending !== null}
              className={primaryButtonClass}
            >
              {pending === "capture" ? "Capturing..." : "Capture Snapshot"}
            </button>
          </div>
        </div>

        {message && (
          <p className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
            {message}
          </p>
        )}

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          <Metric label="NAV" value={money(snapshot.nav)} />
          <Metric label="Cash" value={`${pct(snapshot.cash_pct)}%`} />
          <Metric label="Gross" value={`${pct(snapshot.gross_exposure_pct)}%`} />
          <Metric label="Volatility" value={optionalPct(snapshot.portfolio_volatility_pct)} />
          <Metric label="VaR 95" value={optionalPct(snapshot.var_95_pct)} />
          <Metric label="Warnings" value={String(failedChecks.length)} tone={failedChecks.length ? "warn" : "ok"} />
        </div>
      </section>

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
        <OverviewPanel overview={overview} />
      )}
      {activeTab === "limits" && (
        <LimitsPanel measurements={overview.measurements} policy={overview.policy.limits} />
      )}
      {activeTab === "stress" && (
        <StressPanel
          customStress={customStress}
          onSubmit={handleStressSubmit}
          pending={pending === "stress"}
          stressTests={overview.stress_tests}
        />
      )}
      {activeTab === "pretrade" && (
        <PreTradePanel
          onSubmit={handlePreTradeSubmit}
          pending={pending === "pretrade"}
          result={preTrade}
        />
      )}
    </div>
  );
}

function OverviewPanel({ overview }: { overview: RiskCentreOverview }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.9fr]">
      <Panel title="Positions" subtitle="Current weights and market-risk estimates">
        <DataTable
          headers={["Ticker", "Weight", "Market value", "Vol.", "Beta", "Liquidity"]}
          rows={overview.positions.map((position) => [
            <div key={position.ticker}>
              <p className="font-medium">{position.ticker}</p>
              <p className="text-xs text-zinc-500">{position.sector ?? position.asset_class}</p>
            </div>,
            `${pct(position.weight_pct)}%`,
            money(position.market_value),
            optionalPct(position.volatility_pct),
            optionalNumber(position.beta_to_benchmark),
            position.liquidity_days ? `${Number(position.liquidity_days).toFixed(2)}d` : "-",
          ])}
          empty="No open positions"
        />
      </Panel>

      <Panel title="Exposure" subtitle="Asset class and sector concentration">
        <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-1">
          <BucketList title="Asset Class" buckets={overview.asset_class_exposure} />
          <BucketList title="Sector" buckets={overview.sector_exposure} />
        </div>
      </Panel>

      <Panel title="Correlation" subtitle="Highest pairwise relationships" className="xl:col-span-2">
        <DataTable
          headers={["Pair", "Correlation"]}
          rows={overview.correlation_pairs.map((pair) => [
            `${pair.ticker_a} / ${pair.ticker_b}`,
            optionalNumber(pair.correlation),
          ])}
          empty="Correlation needs overlapping price history"
        />
      </Panel>

      {overview.notes.length > 0 && (
        <Panel title="Data Notes" subtitle="Coverage and model limitations" className="xl:col-span-2">
          <div className="space-y-2">
            {overview.notes.map((note) => (
              <p key={note} className="text-sm text-zinc-600 dark:text-zinc-400">
                {note}
              </p>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

function LimitsPanel({
  measurements,
  policy,
}: {
  measurements: RiskMeasurement[];
  policy: RiskCentreOverview["policy"]["limits"];
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.8fr]">
      <Panel title="Limit Checks" subtitle="Observed risk against active policy">
        <DataTable
          headers={["Limit", "Observed", "Threshold", "Severity", "Status"]}
          rows={measurements.map((check) => [
            <div key={check.key}>
              <p className="font-medium">{check.name}</p>
              <p className="text-xs text-zinc-500">{check.message}</p>
            </div>,
            check.value === null ? "-" : `${pct(check.value)} ${check.unit}`,
            check.threshold_value === null ? "-" : `${pct(check.threshold_value)} ${check.unit}`,
            formatLabel(check.severity),
            <StatusPill key={`${check.key}-status`} passed={check.passed} />,
          ])}
          empty="No limit checks"
        />
      </Panel>

      <Panel title="Policy" subtitle="Current phase-one hierarchy">
        <div className="space-y-3">
          {policy.map((limit) => (
            <div key={limit.key} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
              <div className="flex items-start justify-between gap-3">
                <p className="text-sm font-medium">{limit.label}</p>
                <span className="text-xs text-zinc-500">{formatLabel(limit.severity)}</span>
              </div>
              <p className="mt-1 text-xs leading-5 text-zinc-500">{limit.description}</p>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function StressPanel({
  customStress,
  onSubmit,
  pending,
  stressTests,
}: {
  customStress: StressTestResult | null;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
  stressTests: StressTestResult[];
}) {
  const allStress = customStress ? [customStress, ...stressTests] : stressTests;

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_0.72fr]">
      <Panel title="Stress Results" subtitle="NAV impact under standard and custom shocks">
        <div className="space-y-5">
          <HorizontalBarPlot
            data={allStress.map((stress) => ({
              label: stress.scenario_name,
              value: Number(stress.nav_impact_pct),
              valueLabel: `${pct(stress.nav_impact_pct)}%`,
              detail: stress.worst_positions[0]?.ticker
                ? `Worst hit: ${stress.worst_positions[0].ticker}`
                : undefined,
              tone: Number(stress.nav_impact_pct) < 0 ? "negative" : "positive",
            }))}
            empty="No stress tests"
          />
          <DataTable
            headers={["Scenario", "NAV after", "Impact", "Severity", "Worst hit"]}
            rows={allStress.map((stress) => [
              stress.scenario_name,
              money(stress.nav_after),
              `${money(stress.nav_impact)} (${pct(stress.nav_impact_pct)}%)`,
              formatLabel(stress.severity),
              stress.worst_positions[0]?.ticker ?? "-",
            ])}
            empty="No stress tests"
          />
        </div>
      </Panel>

      <Panel title="Custom Scenario" subtitle="Run an immediate shock test">
        <form onSubmit={onSubmit} className="space-y-3">
          <Field label="Name">
            <input name="name" defaultValue="Custom risk-off" className={inputClass} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Market Shock %">
              <input name="market_shock_pct" defaultValue="-8" className={inputClass} />
            </Field>
            <Field label="Cash Shock % NAV">
              <input name="cash_shock_pct" defaultValue="0" className={inputClass} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Ticker">
              <TickerCombobox name="ticker" className={inputClass} />
            </Field>
            <Field label="Ticker Shock %">
              <input name="ticker_shock_pct" className={inputClass} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Sector">
              <input name="sector" className={inputClass} />
            </Field>
            <Field label="Sector Shock %">
              <input name="sector_shock_pct" className={inputClass} />
            </Field>
          </div>
          <Field label="Notes">
            <textarea name="notes" rows={2} className={inputClass} />
          </Field>
          <button type="submit" disabled={pending} className={primaryButtonClass}>
            {pending ? "Running..." : "Run Scenario"}
          </button>
        </form>
      </Panel>
    </div>
  );
}

function PreTradePanel({
  onSubmit,
  pending,
  result,
}: {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  pending: boolean;
  result: PreTradeRiskCheck | null;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-[0.8fr_1fr]">
      <Panel title="Pro-Forma Trade" subtitle="Check risk before the trade journal">
        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Ticker">
              <TickerCombobox name="ticker" required className={inputClass} />
            </Field>
            <Field label="Name">
              <input name="name" className={inputClass} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Side">
              <select name="side" defaultValue="buy" className={inputClass}>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </Field>
            <Field label="Quantity">
              <input name="quantity" required className={inputClass} />
            </Field>
            <Field label="Price">
              <input name="price" required className={inputClass} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Fees">
              <input name="fees" defaultValue="0" className={inputClass} />
            </Field>
            <Field label="Asset Class">
              <select name="asset_class" defaultValue="equity" className={inputClass}>
                <option value="equity">Equity</option>
                <option value="etf">ETF</option>
                <option value="bond">Bond</option>
                <option value="commodity">Commodity</option>
                <option value="cash_equivalent">Cash Equivalent</option>
                <option value="other">Other</option>
              </select>
            </Field>
            <Field label="Currency">
              <input name="currency" defaultValue="USD" className={`${inputClass} uppercase`} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Exchange">
              <input name="exchange" className={inputClass} />
            </Field>
            <Field label="Sector">
              <input name="sector" className={inputClass} />
            </Field>
            <Field label="Industry">
              <input name="industry" className={inputClass} />
            </Field>
          </div>
          <Field label="Rationale">
            <textarea name="rationale" rows={2} className={inputClass} />
          </Field>
          <button type="submit" disabled={pending} className={primaryButtonClass}>
            {pending ? "Checking..." : "Check Trade"}
          </button>
        </form>
      </Panel>

      <Panel title="Decision" subtitle="Policy and stress impact after the proposed trade">
        {result ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-4">
              <Metric label="Decision" value={formatLabel(result.decision)} />
              <Metric label="Risk Level" value={formatLabel(result.risk_level)} />
              <Metric label="Cash Impact" value={money(result.cash_impact)} />
              <Metric label="Pro-Forma NAV" value={money(result.pro_forma_snapshot.nav)} />
            </div>
            {result.messages.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950">
                {result.messages.map((item) => (
                  <p key={item} className="text-sm text-amber-800 dark:text-amber-200">
                    {item}
                  </p>
                ))}
              </div>
            )}
            <DataTable
              headers={["Check", "Observed", "Status"]}
              rows={result.checks.map((check) => [
                check.name,
                check.value === null ? "-" : `${pct(check.value)} ${check.unit}`,
                <StatusPill key={`${check.key}-pre`} passed={check.passed} />,
              ])}
              empty="No checks"
            />
          </div>
        ) : (
          <p className="text-sm text-zinc-500">No pre-trade check yet</p>
        )}
      </Panel>
    </div>
  );
}

function BucketList({
  buckets,
  title,
}: {
  buckets: RiskCentreOverview["asset_class_exposure"];
  title: string;
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <HorizontalBarPlot
        data={buckets.map((bucket) => ({
          label: formatLabel(bucket.name),
          value: Number(bucket.exposure_pct),
          valueLabel: `${pct(bucket.exposure_pct)}%`,
          detail: money(bucket.market_value),
          tone: "neutral",
        }))}
        empty="No exposure"
      />
    </div>
  );
}

function Panel({
  children,
  className = "",
  subtitle,
  title,
}: {
  children: React.ReactNode;
  className?: string;
  subtitle: string;
  title: string;
}) {
  return (
    <section className={`overflow-hidden rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950 ${className}`}>
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-0.5 text-sm text-zinc-500">{subtitle}</p>
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Metric({
  label,
  tone,
  value,
}: {
  label: string;
  tone?: "ok" | "warn";
  value: string;
}) {
  return (
    <div className="rounded-lg border border-zinc-200 px-3.5 py-3 dark:border-zinc-800">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className={`mt-1.5 text-lg font-semibold tabular-nums ${
        tone === "warn" ? "text-amber-700 dark:text-amber-300" : ""
      } ${tone === "ok" ? "text-emerald-700 dark:text-emerald-300" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function Field({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <label className="block text-sm">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </span>
      {children}
    </label>
  );
}

function DataTable({
  empty,
  headers,
  rows,
}: {
  empty: string;
  headers: string[];
  rows: React.ReactNode[][];
}) {
  if (rows.length === 0) {
    return <p className="text-sm text-zinc-500">{empty}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[680px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800">
            {headers.map((header) => (
              <th
                key={header}
                className="pb-3 pr-4 text-xs font-medium uppercase tracking-wide text-zinc-500 last:pr-0"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-zinc-100 last:border-0 dark:border-zinc-900">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="py-3 pr-4 text-zinc-800 last:pr-0 dark:text-zinc-200">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusPill({ passed }: { passed: boolean }) {
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-xs font-medium ${
      passed
        ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
        : "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300"
    }`}>
      {passed ? "Pass" : "Review"}
    </span>
  );
}

function textValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}

function assetClassValue(formData: FormData): PreTradeRiskInput["instrument"]["asset_class"] {
  const value = textValue(formData, "asset_class");
  if (value === "etf" || value === "bond" || value === "commodity" || value === "cash_equivalent" || value === "other") {
    return value;
  }
  return "equity";
}

function sideValue(formData: FormData): "buy" | "sell" {
  return textValue(formData, "side") === "sell" ? "sell" : "buy";
}

function money(value: string) {
  return currency.format(Number(value));
}

function pct(value: string) {
  return Number(value).toFixed(2);
}

function optionalPct(value: string | null) {
  return value === null ? "-" : `${Number(value).toFixed(2)}%`;
}

function optionalNumber(value: string | null) {
  return value === null ? "-" : Number(value).toFixed(3);
}

function formatLabel(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

const inputClass =
  "w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-zinc-500 dark:border-zinc-800 dark:bg-zinc-950";

const primaryButtonClass =
  "rounded-md bg-zinc-950 px-3 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60 dark:bg-zinc-100 dark:text-zinc-950";

const secondaryButtonClass =
  "rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm font-medium text-zinc-700 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300";
