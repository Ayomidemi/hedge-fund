"use client";

import { useMemo, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  captureStrategyPodSnapshot,
  getStrategyPods,
  updateStrategyPod,
  type StrategyPod,
  type StrategyPodsOverview,
  type StrategyPodUpdateInput,
} from "@/lib/api";

type StrategyPodsProps = {
  initialOverview: StrategyPodsOverview | null;
  unavailable: boolean;
};

type PodFormState = {
  status: string;
  lifecycle_stage: string;
  capital_allocation_pct: string;
  risk_budget_pct: string;
  volatility_target_pct: string;
  max_drawdown_pct: string;
  turnover_ceiling_pct: string;
  approved_instruments: string;
  shutdown_criteria: string;
  notes: string;
};

const statusOptions = ["active", "watch", "research", "sandbox", "suspended", "retired"];
const lifecycleOptions = [
  "research",
  "candidate",
  "paper_trading",
  "probationary_capital",
  "core_strategy",
  "reduced_allocation",
  "suspended",
  "retired",
];

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

export function StrategyPods({ initialOverview, unavailable }: StrategyPodsProps) {
  const [overview, setOverview] = useState<StrategyPodsOverview | null>(initialOverview);
  const [selectedCode, setSelectedCode] = useState(initialOverview?.pods[0]?.code ?? "");
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [capturing, setCapturing] = useState(false);

  const selectedPod = useMemo(() => {
    return overview?.pods.find((pod) => pod.code === selectedCode) ?? overview?.pods[0] ?? null;
  }, [overview, selectedCode]);

  async function refreshOverview() {
    setLoading(true);
    setMessage(null);
    try {
      const nextOverview = await getStrategyPods();
      setOverview(nextOverview);
      if (!nextOverview.pods.some((pod) => pod.code === selectedCode)) {
        setSelectedCode(nextOverview.pods[0]?.code ?? "");
      }
    } catch {
      setMessage("Strategy pods could not be refreshed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(payload: StrategyPodUpdateInput) {
    if (!selectedPod) return;

    setSaving(true);
    setMessage(null);
    try {
      await updateStrategyPod(selectedPod.code, payload);
      await refreshOverview();
      setMessage(`${selectedPod.name} controls saved.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Strategy pod could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCaptureSnapshot() {
    if (!selectedPod) return;

    setCapturing(true);
    setMessage(null);
    try {
      const snapshot = await captureStrategyPodSnapshot(selectedPod.code);
      await refreshOverview();
      setMessage(`Snapshot captured for ${formatLabel(snapshot.code)} on ${formatDate(snapshot.as_of_date)}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Snapshot could not be captured.");
    } finally {
      setCapturing(false);
    }
  }

  if (!overview) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {unavailable
          ? "Backend unavailable. Check the API server and refresh this page."
          : "Strategy pods are not available yet."}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {overview.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Strategy Pods</h2>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={formatLabel(overview.risk_level)} tone={riskTone(overview.risk_level)} />
            <button
              type="button"
              onClick={refreshOverview}
              disabled={loading}
              className={buttonSecondaryClassName}
            >
              {loading ? "Refreshing" : "Refresh"}
            </button>
          </div>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-5 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
          <Metric label="NAV" value={money(overview.nav)} />
          <Metric label="Allocated" value={pct(overview.allocation_total_pct)} />
          <Metric label="Reserve" value={pct(overview.unallocated_pct)} />
          <Metric label="Risk Budget" value={pct(overview.risk_budget_total_pct)} />
          <Metric label="Pods" value={String(overview.pods.length)} />
        </div>
      </section>

      {(overview.warnings.length > 0 || message) && (
        <section className="rounded-lg border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900 dark:border-amber-900/70 dark:bg-amber-950/40 dark:text-amber-100">
          {message && <p className="font-medium">{message}</p>}
          {overview.warnings.map((warning) => (
            <p key={warning} className={message ? "mt-1" : ""}>
              {warning}
            </p>
          ))}
        </section>
      )}

      <div className="grid gap-5 xl:grid-cols-[0.95fr_1.45fr]">
        <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Pod book
            </p>
            <h3 className="mt-1 text-lg font-semibold">Capital and signal view</h3>
          </div>
          <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {overview.pods.map((pod) => (
              <button
                key={pod.code}
                type="button"
                onClick={() => setSelectedCode(pod.code)}
                className={`block w-full px-5 py-4 text-left transition ${
                  selectedPod?.code === pod.code
                    ? "bg-zinc-50 dark:bg-zinc-900/70"
                    : "hover:bg-zinc-50 dark:hover:bg-zinc-900/50"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium">{pod.name}</p>
                    <p className="mt-1 line-clamp-2 text-sm leading-6 text-zinc-500">
                      {pod.mandate}
                    </p>
                  </div>
                  <StatusBadge label={formatLabel(pod.status)} tone={statusTone(pod.status)} />
                </div>
                <div className="mt-4 grid grid-cols-3 gap-3 text-xs">
                  <MiniMetric label="Allocation" value={pct(pod.capital_allocation_pct)} />
                  <MiniMetric label="Signal" value={scoreText(pod.current_signal_score)} />
                  <MiniMetric label="Confidence" value={scoreText(pod.model_confidence)} />
                </div>
              </button>
            ))}
          </div>
        </section>

        {selectedPod && (
          <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                  Selected pod
                </p>
                <h3 className="mt-1 text-lg font-semibold">{selectedPod.name}</h3>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={handleCaptureSnapshot}
                  disabled={capturing}
                  className={buttonSecondaryClassName}
                >
                  {capturing ? "Capturing" : "Capture snapshot"}
                </button>
              </div>
            </div>

            <div className="grid gap-0 xl:grid-cols-[1fr_0.95fr] xl:divide-x xl:divide-zinc-200 dark:xl:divide-zinc-800">
              <div className="px-5 py-5">
                <PodControlForm
                  key={selectedPod.code}
                  pod={selectedPod}
                  saving={saving}
                  onSave={handleSave}
                />
              </div>

              <div className="divide-y divide-zinc-200 dark:divide-zinc-800">
                <PodEvidence pod={selectedPod} />
                <PodGovernance pod={selectedPod} />
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

function PodControlForm({
  pod,
  saving,
  onSave,
}: {
  pod: StrategyPod;
  saving: boolean;
  onSave: (payload: StrategyPodUpdateInput) => void;
}) {
  const [formState, setFormState] = useState<PodFormState>(() => buildFormState(pod));

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSave(buildUpdatePayload(formState));
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <p className="text-sm font-semibold">Mandate</p>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{pod.mandate}</p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Status">
          <select
            name="status"
            value={formState.status}
            onChange={(event) => setFormStateValue(setFormState, "status", event.target.value)}
            className={inputClassName}
          >
            {statusOptions.map((option) => (
              <option key={option} value={option}>
                {formatLabel(option)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Lifecycle">
          <select
            name="lifecycle_stage"
            value={formState.lifecycle_stage}
            onChange={(event) => setFormStateValue(setFormState, "lifecycle_stage", event.target.value)}
            className={inputClassName}
          >
            {lifecycleOptions.map((option) => (
              <option key={option} value={option}>
                {formatLabel(option)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Capital Allocation %">
          <input
            name="capital_allocation_pct"
            value={formState.capital_allocation_pct}
            onChange={(event) => setFormStateValue(setFormState, "capital_allocation_pct", event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
        <Field label="Risk Budget %">
          <input
            name="risk_budget_pct"
            value={formState.risk_budget_pct}
            onChange={(event) => setFormStateValue(setFormState, "risk_budget_pct", event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
        <Field label="Volatility Target %">
          <input
            name="volatility_target_pct"
            value={formState.volatility_target_pct}
            onChange={(event) => setFormStateValue(setFormState, "volatility_target_pct", event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
        <Field label="Max Drawdown %">
          <input
            name="max_drawdown_pct"
            value={formState.max_drawdown_pct}
            onChange={(event) => setFormStateValue(setFormState, "max_drawdown_pct", event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
        <Field label="Turnover Ceiling %">
          <input
            name="turnover_ceiling_pct"
            value={formState.turnover_ceiling_pct}
            onChange={(event) => setFormStateValue(setFormState, "turnover_ceiling_pct", event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
      </div>

      <Field label="Approved Instruments">
        <textarea
          name="approved_instruments"
          value={formState.approved_instruments}
          onChange={(event) => setFormStateValue(setFormState, "approved_instruments", event.target.value)}
          className={`${inputClassName} min-h-24 resize-y`}
        />
      </Field>

      <Field label="Shutdown Criteria">
        <textarea
          name="shutdown_criteria"
          value={formState.shutdown_criteria}
          onChange={(event) => setFormStateValue(setFormState, "shutdown_criteria", event.target.value)}
          className={`${inputClassName} min-h-24 resize-y`}
        />
      </Field>

      <Field label="Notes">
        <textarea
          name="notes"
          value={formState.notes}
          onChange={(event) => setFormStateValue(setFormState, "notes", event.target.value)}
          className={`${inputClassName} min-h-20 resize-y`}
        />
      </Field>

      <div className="flex justify-end">
        <button type="submit" disabled={saving} className={buttonPrimaryClassName}>
          {saving ? "Saving" : "Save controls"}
        </button>
      </div>
    </form>
  );
}

function PodEvidence({ pod }: { pod: StrategyPod }) {
  const currentSignals = pod.current_signals as {
    primary_model?: unknown;
    required_inputs?: unknown;
  };
  const evaluation = pod.evaluation as {
    primary_question?: unknown;
    minimum_evidence?: unknown;
    live?: Record<string, unknown>;
  };

  return (
    <div className="px-5 py-5">
      <div className="grid gap-3 sm:grid-cols-3">
        <MiniMetric label="Signal" value={scoreText(pod.current_signal_score)} />
        <MiniMetric label="Confidence" value={scoreText(pod.model_confidence)} />
        <MiniMetric label="Risk" value={formatLabel(pod.risk_level)} />
      </div>

      <div className="mt-5">
        <p className="text-sm font-semibold">Allocation recommendation</p>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {pod.allocation_recommendation}
        </p>
      </div>

      <div className="mt-5">
        <p className="text-sm font-semibold">Live evidence</p>
        <div className="mt-3 divide-y divide-zinc-100 dark:divide-zinc-900">
          {pod.live_signals.map((signal) => (
            <div key={signal.key} className="py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-medium">{signal.label}</p>
                  <p className="mt-1 text-xs text-zinc-500">{signal.detail ?? "No detail available."}</p>
                </div>
                <StatusBadge label={signal.value} tone={signalTone(signal.status)} />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5">
        <p className="text-sm font-semibold">Model and gates</p>
        <dl className="mt-3 space-y-3 text-sm">
          <KeyValue label="Primary model" value={stringValue(currentSignals.primary_model)} />
          <KeyValue label="Primary question" value={stringValue(evaluation.primary_question)} />
          <KeyValue label="Required inputs" value={listValue(currentSignals.required_inputs)} />
          <KeyValue label="Minimum evidence" value={listValue(evaluation.minimum_evidence)} />
        </dl>
      </div>

      {evaluation.live && (
        <div className="mt-5">
          <p className="text-sm font-semibold">Current readout</p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            {Object.entries(evaluation.live).slice(0, 8).map(([key, value]) => (
              <KeyValue key={key} label={formatLabel(key)} value={compactValue(value)} />
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

function PodGovernance({ pod }: { pod: StrategyPod }) {
  return (
    <div className="px-5 py-5">
      <p className="text-sm font-semibold">Governance</p>
      <div className="mt-4 space-y-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Approved instruments
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {pod.approved_instruments.map((instrument) => (
              <span
                key={instrument}
                className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-300"
              >
                {instrument}
              </span>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Shutdown criteria
          </p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            {pod.shutdown_criteria ?? "No shutdown criteria recorded."}
          </p>
        </div>

        {pod.open_risk_warnings.length > 0 && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
              Open risk warnings
            </p>
            <ul className="mt-2 space-y-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
              {pod.open_risk_warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Latest snapshot
          </p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
            {pod.latest_snapshot
              ? `${formatDate(pod.latest_snapshot.as_of_date)} at ${formatTime(pod.latest_snapshot.captured_at)}`
              : "No pod snapshot captured yet."}
          </p>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="px-5 py-4">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      {label}
      {children}
    </label>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="mt-1 text-sm leading-6 text-zinc-700 dark:text-zinc-300">{value}</dd>
    </div>
  );
}

function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: string }) {
  const className =
    tone === "good"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
      : tone === "bad"
        ? "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300"
        : tone === "warn"
          ? "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300"
          : "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300";

  return (
    <span className={`shrink-0 rounded-md px-2.5 py-1 text-xs font-medium ${className}`}>
      {label}
    </span>
  );
}

function setFormStateValue(
  setFormState: Dispatch<SetStateAction<PodFormState>>,
  key: keyof PodFormState,
  value: string,
) {
  setFormState((current) => ({ ...current, [key]: value }));
}

function buildFormState(pod: StrategyPod | null): PodFormState {
  return {
    status: pod?.status ?? "research",
    lifecycle_stage: pod?.lifecycle_stage ?? "research",
    capital_allocation_pct: cleanNumber(pod?.capital_allocation_pct),
    risk_budget_pct: cleanNumber(pod?.risk_budget_pct),
    volatility_target_pct: cleanNumber(pod?.volatility_target_pct),
    max_drawdown_pct: cleanNumber(pod?.max_drawdown_pct),
    turnover_ceiling_pct: cleanNumber(pod?.turnover_ceiling_pct),
    approved_instruments: pod?.approved_instruments.join(", ") ?? "",
    shutdown_criteria: pod?.shutdown_criteria ?? "",
    notes: pod?.notes ?? "",
  };
}

function buildUpdatePayload(formState: PodFormState): StrategyPodUpdateInput {
  return {
    status: formState.status,
    lifecycle_stage: formState.lifecycle_stage,
    capital_allocation_pct: numberOrZero(formState.capital_allocation_pct),
    risk_budget_pct: numberOrZero(formState.risk_budget_pct),
    volatility_target_pct: nullableNumber(formState.volatility_target_pct),
    max_drawdown_pct: nullableNumber(formState.max_drawdown_pct),
    turnover_ceiling_pct: nullableNumber(formState.turnover_ceiling_pct),
    approved_instruments: formState.approved_instruments
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
    shutdown_criteria: formState.shutdown_criteria.trim() || null,
    notes: formState.notes.trim() || null,
  };
}

function cleanNumber(value: string | null | undefined) {
  if (!value) return "";
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return String(Number(number.toFixed(4)));
}

function numberOrZero(value: string) {
  return nullableNumber(value) ?? "0";
}

function nullableNumber(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function money(value: string) {
  return currency.format(Number(value));
}

function pct(value: string | null) {
  if (value === null) return "Pending";
  return `${Number(value).toFixed(1)}%`;
}

function scoreText(value: string | null) {
  if (value === null) return "Pending";
  return `${Number(value).toFixed(0)}/100`;
}

function formatLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replaceAll("-", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(value));
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function riskTone(value: string) {
  if (["halt", "suspend", "reduce"].includes(value)) return "bad";
  if (value === "warning") return "warn";
  return "good";
}

function statusTone(value: string) {
  if (["active", "core_strategy"].includes(value)) return "good";
  if (["suspended", "retired"].includes(value)) return "bad";
  if (["watch", "candidate", "paper_trading"].includes(value)) return "warn";
  return "neutral";
}

function signalTone(value: string) {
  if (value === "live") return "good";
  if (["warning", "pending"].includes(value)) return "warn";
  return "neutral";
}

function stringValue(value: unknown) {
  return typeof value === "string" && value ? value : "Pending";
}

function listValue(value: unknown) {
  if (!Array.isArray(value) || value.length === 0) return "Pending";
  return value.map((item) => String(item)).join(", ");
}

function compactValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "Pending";
  if (Array.isArray(value)) return value.map((item) => String(item)).join(", ") || "Pending";
  if (typeof value === "object") return `${Object.keys(value).length} item${Object.keys(value).length === 1 ? "" : "s"}`;
  return String(value);
}
