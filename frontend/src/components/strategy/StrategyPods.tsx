"use client";

import { useEffect, useMemo, useState } from "react";
import type { Dispatch, FormEvent, ReactNode, SetStateAction } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  captureStrategyPodSnapshot,
  getStrategyPodSnapshots,
  getStrategyPods,
  updateStrategyPod,
  type StrategyPod,
  type StrategyPodSnapshot,
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
  const [selectedCode, setSelectedCode] = useState(() => {
    const alpha =
      initialOverview?.alpha_pods ??
      initialOverview?.pods.filter((pod) => pod.pod_category === "alpha") ??
      [];
    return alpha[0]?.code ?? initialOverview?.pods[0]?.code ?? "";
  });
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [showControls, setShowControls] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [snapshots, setSnapshots] = useState<StrategyPodSnapshot[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const selectedPod = useMemo(() => {
    return overview?.pods.find((pod) => pod.code === selectedCode) ?? overview?.pods[0] ?? null;
  }, [overview, selectedCode]);

  const podGroups = useMemo(() => {
    if (!overview) return [];
    const alpha = overview.alpha_pods ?? overview.pods.filter((p) => p.pod_category === "alpha");
    const hedge = overview.hedge_pods ?? overview.pods.filter((p) => p.pod_category === "hedge");
    const treasury =
      overview.treasury_pods ?? overview.pods.filter((p) => p.pod_category === "treasury");
    return [
      { label: "Alpha", pods: alpha },
      { label: "Hedge", pods: hedge },
      { label: "Treasury", pods: treasury },
    ].filter((group) => group.pods.length > 0);
  }, [overview]);

  useEffect(() => {
    if (!showHistory || !selectedPod?.code) return;

    let cancelled = false;
    const podCode = selectedPod.code;

    async function loadSnapshots() {
      setHistoryLoading(true);
      try {
        const items = await getStrategyPodSnapshots(podCode);
        if (!cancelled) setSnapshots(items);
      } catch {
        if (!cancelled) {
          setSnapshots([]);
          toast.error("Snapshot history could not be loaded.");
        }
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }

    void loadSnapshots();
    return () => {
      cancelled = true;
    };
  }, [showHistory, selectedPod?.code]);

  async function reloadOverview(options?: { notify?: boolean }) {
    setLoading(true);
    try {
      const nextOverview = await getStrategyPods();
      setOverview(nextOverview);
      if (!nextOverview.pods.some((pod) => pod.code === selectedCode)) {
        const nextAlpha =
          nextOverview.alpha_pods ??
          nextOverview.pods.filter((pod) => pod.pod_category === "alpha");
        setSelectedCode(nextAlpha[0]?.code ?? nextOverview.pods[0]?.code ?? "");
      }
      if (options?.notify) toast.success("Strategy pods refreshed.");
    } catch {
      if (options?.notify) toast.error("Strategy pods could not be refreshed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(payload: StrategyPodUpdateInput) {
    if (!selectedPod) return;
    setSaving(true);
    try {
      await updateStrategyPod(selectedPod.code, payload);
      await reloadOverview();
      toast.success(`${selectedPod.name} updated.`);
      setShowControls(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Strategy pod could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCaptureSnapshot() {
    if (!selectedPod) return;
    setCapturing(true);
    try {
      const snapshot = await captureStrategyPodSnapshot(selectedPod.code);
      await reloadOverview();
      if (showHistory) {
        setSnapshots(await getStrategyPodSnapshots(selectedPod.code));
      }
      toast.success(`Snapshot captured for ${formatDate(snapshot.as_of_date)}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Snapshot could not be captured.");
    } finally {
      setCapturing(false);
    }
  }

  if (!overview) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {unavailable
          ? "Strategy pods could not be loaded yet. Sign in again or refresh this page."
          : "Strategy pods are not available yet."}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Investment book
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Strategy Pods</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Alpha generates return · Hedge removes unintended risk · Treasury holds liquidity
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge label={formatLabel(overview.risk_level)} tone={riskTone(overview.risk_level)} />
            <button
              type="button"
              onClick={() => void reloadOverview({ notify: true })}
              disabled={loading}
              className={buttonSecondaryClassName}
            >
              {loading ? "Refreshing" : "Refresh"}
            </button>
          </div>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-4 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
          <Metric label="NAV" value={money(overview.nav)} />
          <Metric label="Alpha allocation" value={pct(overview.alpha_allocation_total_pct)} />
          <Metric label="Cash" value={overview.cash_pct ? pct(overview.cash_pct) : "—"} />
          <Metric label="Treasury target" value={pct(overview.treasury_target_pct)} />
        </div>

        {overview.warnings.length > 0 && (
          <div className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
            <ul className="space-y-1 text-sm text-amber-800 dark:text-amber-200">
              {overview.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(280px,340px)_1fr]">
        <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <h3 className="text-sm font-semibold">Books</h3>
          </div>
          <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {podGroups.map((group) => (
              <div key={group.label}>
                <p className="px-4 pt-3 pb-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
                  {group.label}
                </p>
                <ul>
                  {group.pods.map((pod) => (
                    <PodListItem
                      key={pod.code}
                      pod={pod}
                      selected={selectedPod?.code === pod.code}
                      onSelect={() => {
                        setSelectedCode(pod.code);
                        setShowControls(false);
                        setShowHistory(false);
                      }}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>

        {selectedPod ? (
          <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
            <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge
                      label={formatLabel(selectedPod.pod_category)}
                      tone={categoryTone(selectedPod.pod_category)}
                    />
                    <StatusBadge
                      label={formatLabel(selectedPod.live_scope)}
                      tone={liveScopeTone(selectedPod.live_scope)}
                    />
                    <StatusBadge
                      label={formatLabel(selectedPod.lifecycle_stage)}
                      tone={statusTone(selectedPod.status)}
                    />
                  </div>
                  <h3 className="mt-2 text-lg font-semibold">{selectedPod.name}</h3>
                  <p className="mt-1 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
                    {selectedPod.mandate}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <button
                    type="button"
                    onClick={() => void handleCaptureSnapshot()}
                    disabled={capturing}
                    className={buttonSecondaryClassName}
                  >
                    {capturing ? "Saving…" : "Snapshot"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowControls((current) => !current)}
                    className={buttonSecondaryClassName}
                  >
                    {showControls ? "Close" : "Edit"}
                  </button>
                </div>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <MiniStat label="Allocation" value={pct(selectedPod.capital_allocation_pct)} />
                <MiniStat label="Signal" value={scoreText(selectedPod.current_signal_score)} />
                <MiniStat label="Confidence" value={scoreText(selectedPod.model_confidence)} />
              </div>

              <div className="mt-4 rounded-lg border border-zinc-200 bg-zinc-50/80 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/40">
                <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
                  Recommendation
                </p>
                <p className="mt-1 text-sm leading-6 text-zinc-800 dark:text-zinc-200">
                  {selectedPod.allocation_recommendation}
                </p>
              </div>
            </div>

            <div className="px-5 py-4">
              <p className="text-sm font-semibold">Live evidence</p>
              <div className="mt-3 space-y-3">
                {selectedPod.live_signals.length === 0 ? (
                  <p className="text-sm text-zinc-500">No live signals yet.</p>
                ) : (
                  selectedPod.live_signals.map((signal) => (
                    <div
                      key={signal.key}
                      className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-3 last:border-0 last:pb-0 dark:border-zinc-900"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{signal.label}</p>
                        {signal.detail ? (
                          <p className="mt-0.5 text-xs leading-5 text-zinc-500">{signal.detail}</p>
                        ) : null}
                      </div>
                      <StatusBadge label={signal.value} tone={signalTone(signal.status)} />
                    </div>
                  ))
                )}
              </div>

              {selectedPod.open_risk_warnings.length > 0 && (
                <div className="mt-5 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 dark:border-amber-900 dark:bg-amber-950/40">
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200">
                    Risk warnings
                  </p>
                  <ul className="mt-2 space-y-1 text-sm text-amber-900 dark:text-amber-100">
                    {selectedPod.open_risk_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}

              {showControls && (
                <div className="mt-5 border-t border-zinc-200 pt-5 dark:border-zinc-800">
                  <ControlsForm pod={selectedPod} saving={saving} onSave={handleSave} />
                </div>
              )}

              <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowHistory((current) => !current)}
                  className="text-sm font-medium text-zinc-700 hover:text-zinc-950 dark:text-zinc-300 dark:hover:text-zinc-100"
                >
                  {showHistory ? "Hide snapshot history" : "Show snapshot history"}
                </button>
                {showHistory && (
                  <SnapshotHistory snapshots={snapshots} loading={historyLoading} />
                )}
              </div>
            </div>
          </section>
        ) : (
          <section className="flex items-center justify-center rounded-xl border border-dashed border-zinc-300 px-5 py-16 text-sm text-zinc-500 dark:border-zinc-700">
            Select a pod to inspect signals and controls.
          </section>
        )}
      </div>
    </div>
  );
}

function PodListItem({
  pod,
  selected,
  onSelect,
}: {
  pod: StrategyPod;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        className={`flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition ${
          selected
            ? "bg-zinc-100 dark:bg-zinc-900"
            : "hover:bg-zinc-50 dark:hover:bg-zinc-900/50"
        }`}
      >
        <div className="min-w-0">
          <p className="truncate text-sm font-medium">{pod.name}</p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {pct(pod.capital_allocation_pct)} · {formatLabel(pod.status)}
          </p>
        </div>
        <span className="shrink-0 text-xs font-semibold tabular-nums text-zinc-600 dark:text-zinc-400">
          {scoreText(pod.current_signal_score)}
        </span>
      </button>
    </li>
  );
}

function ControlsForm({
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm font-semibold">Pod controls</p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Status">
          <select
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
            value={formState.lifecycle_stage}
            onChange={(event) =>
              setFormStateValue(setFormState, "lifecycle_stage", event.target.value)
            }
            className={inputClassName}
          >
            {lifecycleOptions.map((option) => (
              <option key={option} value={option}>
                {formatLabel(option)}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Capital allocation %">
          <input
            value={formState.capital_allocation_pct}
            onChange={(event) =>
              setFormStateValue(setFormState, "capital_allocation_pct", event.target.value)
            }
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
        <Field label="Risk budget %">
          <input
            value={formState.risk_budget_pct}
            onChange={(event) =>
              setFormStateValue(setFormState, "risk_budget_pct", event.target.value)
            }
            className={inputClassName}
            inputMode="decimal"
          />
        </Field>
      </div>
      <Field label="Notes">
        <textarea
          value={formState.notes}
          onChange={(event) => setFormStateValue(setFormState, "notes", event.target.value)}
          className={`${inputClassName} min-h-20 resize-y`}
        />
      </Field>
      <div className="flex justify-end">
        <button type="submit" disabled={saving} className={buttonPrimaryClassName}>
          {saving ? "Saving" : "Save changes"}
        </button>
      </div>
    </form>
  );
}

function SnapshotHistory({
  snapshots,
  loading,
}: {
  snapshots: StrategyPodSnapshot[];
  loading: boolean;
}) {
  if (loading) {
    return <p className="mt-3 text-sm text-zinc-500">Loading history…</p>;
  }
  if (snapshots.length === 0) {
    return <p className="mt-3 text-sm text-zinc-500">No snapshots captured yet.</p>;
  }

  return (
    <div className="mt-3 overflow-x-auto">
      <table className="w-full min-w-[520px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800">
            <th className="py-2 pr-3 font-medium">Date</th>
            <th className="py-2 pr-3 font-medium">Alloc</th>
            <th className="py-2 pr-3 font-medium">Signal</th>
            <th className="py-2 font-medium">Recommendation</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {snapshots.map((snapshot) => (
            <tr key={snapshot.snapshot_id}>
              <td className="py-2.5 pr-3 whitespace-nowrap">{formatDate(snapshot.as_of_date)}</td>
              <td className="py-2.5 pr-3 tabular-nums">{pct(snapshot.capital_allocation_pct)}</td>
              <td className="py-2.5 pr-3 tabular-nums">{scoreText(snapshot.current_signal_score)}</td>
              <td className="py-2.5 line-clamp-2 text-zinc-600 dark:text-zinc-400">
                {snapshot.allocation_recommendation}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
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

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-800">
      <p className="text-[11px] font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 text-sm font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      <span className="mb-1.5 block">{label}</span>
      {children}
    </label>
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
    <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${className}`}>
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

function buildFormState(pod: StrategyPod): PodFormState {
  return {
    status: pod.status,
    lifecycle_stage: pod.lifecycle_stage,
    capital_allocation_pct: cleanNumber(pod.capital_allocation_pct),
    risk_budget_pct: cleanNumber(pod.risk_budget_pct),
    volatility_target_pct: cleanNumber(pod.volatility_target_pct),
    max_drawdown_pct: cleanNumber(pod.max_drawdown_pct),
    turnover_ceiling_pct: cleanNumber(pod.turnover_ceiling_pct),
    approved_instruments: pod.approved_instruments.join(", "),
    shutdown_criteria: pod.shutdown_criteria ?? "",
    notes: pod.notes ?? "",
  };
}

function buildUpdatePayload(formState: PodFormState): StrategyPodUpdateInput {
  return {
    status: formState.status,
    lifecycle_stage: formState.lifecycle_stage,
    capital_allocation_pct: numberOrZero(formState.capital_allocation_pct),
    risk_budget_pct: numberOrZero(formState.risk_budget_pct),
    notes: formState.notes.trim() || null,
  };
}

function cleanNumber(value: string | null | undefined) {
  if (!value) return "";
  const number = Number(value);
  return Number.isFinite(number) ? String(Number(number.toFixed(4))) : "";
}

function numberOrZero(value: string) {
  const trimmed = value.trim();
  return trimmed || "0";
}

function money(value: string) {
  return currency.format(Number(value));
}

function pct(value: string | null) {
  if (value === null) return "—";
  return `${Number(value).toFixed(1)}%`;
}

function scoreText(value: string | null) {
  if (value === null) return "—";
  return `${Number(value).toFixed(0)}`;
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

function categoryTone(value: string) {
  if (value === "alpha") return "good";
  if (value === "hedge") return "warn";
  return "neutral";
}

function liveScopeTone(value: string) {
  if (value === "yes") return "good";
  if (value === "limited" || value === "paper") return "warn";
  return "neutral";
}

function riskTone(value: string) {
  if (["halt", "suspend", "reduce"].includes(value)) return "bad";
  if (value === "warning") return "warn";
  return "good";
}

function statusTone(value: string) {
  if (["active", "core_strategy"].includes(value)) return "good";
  if (["suspended", "retired"].includes(value)) return "bad";
  if (["watch", "candidate", "paper_trading", "probationary_capital"].includes(value)) return "warn";
  return "neutral";
}

function signalTone(value: string) {
  if (value === "live") return "good";
  if (value === "warning" || value === "pending") return "warn";
  return "neutral";
}
