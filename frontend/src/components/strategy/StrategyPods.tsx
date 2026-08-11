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

type PodDetailTab = "overview" | "history" | "governance" | "controls";

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

type SortKey = "allocation" | "signal" | "confidence" | "name";

const detailTabs: { key: PodDetailTab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "history", label: "History" },
  { key: "governance", label: "Governance" },
  { key: "controls", label: "Controls" },
];

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
  const [detailTab, setDetailTab] = useState<PodDetailTab>("overview");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortKey, setSortKey] = useState<SortKey>("allocation");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [capturing, setCapturing] = useState(false);
  const [snapshots, setSnapshots] = useState<StrategyPodSnapshot[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const selectedPod = useMemo(() => {
    return overview?.pods.find((pod) => pod.code === selectedCode) ?? overview?.pods[0] ?? null;
  }, [overview, selectedCode]);
  const selectedPodCode = selectedPod?.code;

  const filteredPods = useMemo(() => {
    if (!overview) return [];
    const pods =
      statusFilter === "all"
        ? overview.pods
        : overview.pods.filter((pod) => pod.status === statusFilter);

    return [...pods].sort((left, right) => {
      if (sortKey === "name") return left.name.localeCompare(right.name);
      if (sortKey === "allocation") {
        return Number(right.capital_allocation_pct) - Number(left.capital_allocation_pct);
      }
      if (sortKey === "signal") {
        return compareScores(right.current_signal_score, left.current_signal_score);
      }
      return compareScores(right.model_confidence, left.model_confidence);
    });
  }, [overview, sortKey, statusFilter]);

  useEffect(() => {
    if (detailTab !== "history" || !selectedPodCode) return;

    let cancelled = false;
    const podCode = selectedPodCode;

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
  }, [detailTab, selectedPodCode]);

  async function reloadOverview(options?: { notify?: boolean }) {
    setLoading(true);
    try {
      const nextOverview = await getStrategyPods();
      setOverview(nextOverview);
      if (!nextOverview.pods.some((pod) => pod.code === selectedCode)) {
        setSelectedCode(nextOverview.pods[0]?.code ?? "");
      }
      if (options?.notify) {
        toast.success("Strategy pods refreshed.");
      }
    } catch {
      if (options?.notify) {
        toast.error("Strategy pods could not be refreshed.");
      }
    } finally {
      setLoading(false);
    }
  }

  async function refreshOverview() {
    await reloadOverview({ notify: true });
  }

  async function handleSave(payload: StrategyPodUpdateInput) {
    if (!selectedPod) return;

    setSaving(true);
    try {
      await updateStrategyPod(selectedPod.code, payload);
      await reloadOverview();
      toast.success(`${selectedPod.name} controls saved.`);
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
      if (detailTab === "history") {
        const items = await getStrategyPodSnapshots(selectedPod.code);
        setSnapshots(items);
      }
      toast.success(
        `Snapshot captured for ${formatLabel(snapshot.code)} on ${formatDate(snapshot.as_of_date)}.`,
      );
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
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {overview.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Strategy Pods</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Capital book · {formatDateTime(overview.generated_at)}
            </p>
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

        <div className="border-t border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Capital stack
            </p>
            <p className="text-xs text-zinc-500">Click a segment to inspect a pod</p>
          </div>
          <CapitalStack
            pods={overview.pods}
            reservePct={overview.unallocated_pct}
            selectedCode={selectedCode}
            onSelect={setSelectedCode}
          />
        </div>

        {overview.warnings.length > 0 && (
          <BookAlerts warnings={overview.warnings} />
        )}
      </section>

      <section className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-end justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Pod book
            </p>
            <h3 className="mt-1 text-lg font-semibold">Comparison matrix</h3>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className={`${inputClassName} mt-0 w-auto min-w-[140px]`}
            >
              <option value="all">All statuses</option>
              {statusOptions.map((option) => (
                <option key={option} value={option}>
                  {formatLabel(option)}
                </option>
              ))}
            </select>
            <select
              value={sortKey}
              onChange={(event) => setSortKey(event.target.value as SortKey)}
              className={`${inputClassName} mt-0 w-auto min-w-[140px]`}
            >
              <option value="allocation">Sort: allocation</option>
              <option value="signal">Sort: signal</option>
              <option value="confidence">Sort: confidence</option>
              <option value="name">Sort: name</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50/80 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50">
              <tr>
                <th className="px-5 py-3 font-medium">Pod</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium">Lifecycle</th>
                <th className="px-5 py-3 font-medium">Alloc</th>
                <th className="px-5 py-3 font-medium">Signal</th>
                <th className="px-5 py-3 font-medium">Confidence</th>
                <th className="px-5 py-3 font-medium">Recommendation</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {filteredPods.map((pod) => {
                const selected = selectedPod?.code === pod.code;
                const attention = recommendationAttention(pod.allocation_recommendation);

                return (
                  <tr
                    key={pod.code}
                    className={`cursor-pointer transition ${
                      selected
                        ? "bg-zinc-50 dark:bg-zinc-900/70"
                        : "hover:bg-zinc-50/70 dark:hover:bg-zinc-900/40"
                    }`}
                    onClick={() => {
                      setSelectedCode(pod.code);
                      setDetailTab("overview");
                    }}
                  >
                    <td className="px-5 py-4">
                      <div>
                        <p className="font-medium">{pod.name}</p>
                        <p className="mt-0.5 line-clamp-1 text-xs text-zinc-500">{pod.mandate}</p>
                      </div>
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge label={formatLabel(pod.status)} tone={statusTone(pod.status)} />
                    </td>
                    <td className="px-5 py-4 text-zinc-600 dark:text-zinc-300">
                      {formatLabel(pod.lifecycle_stage)}
                    </td>
                    <td className="px-5 py-4 font-semibold tabular-nums">
                      {pct(pod.capital_allocation_pct)}
                    </td>
                    <td className="px-5 py-4">
                      <ScoreGauge value={pod.current_signal_score} compact />
                    </td>
                    <td className="px-5 py-4">
                      <ScoreGauge value={pod.model_confidence} compact />
                    </td>
                    <td className="px-5 py-4">
                      <div className="flex items-start gap-2">
                        {attention === "action" && (
                          <span className="mt-0.5 h-2 w-2 shrink-0 rounded-full bg-amber-500" />
                        )}
                        <p className="line-clamp-2 max-w-xs text-zinc-600 dark:text-zinc-300">
                          {pod.allocation_recommendation}
                        </p>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
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
              <p className="mt-1 text-sm text-zinc-500">{formatLabel(selectedPod.code)}</p>
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

          <nav className="flex gap-2 overflow-x-auto border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
            {detailTabs.map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => setDetailTab(tab.key)}
                className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                  detailTab === tab.key
                    ? "bg-zinc-950 font-medium text-white dark:bg-zinc-100 dark:text-zinc-950"
                    : "border border-zinc-200 bg-white text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>

          {detailTab === "overview" && <OverviewPanel pod={selectedPod} />}
          {detailTab === "history" && (
            <HistoryPanel pod={selectedPod} snapshots={snapshots} loading={historyLoading} />
          )}
          {detailTab === "governance" && <GovernancePanel pod={selectedPod} />}
          {detailTab === "controls" && (
            <ControlsPanel key={selectedPod.code} pod={selectedPod} saving={saving} onSave={handleSave} />
          )}
        </section>
      )}
    </div>
  );
}

function BookAlerts({ warnings }: { warnings: string[] }) {
  return (
    <div className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
      <ul className="space-y-2">
        {warnings.map((warning) => (
          <li
            key={warning}
            className="text-sm leading-6 text-zinc-600 dark:text-zinc-400"
          >
            {warning}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CapitalStack({
  pods,
  reservePct,
  selectedCode,
  onSelect,
}: {
  pods: StrategyPod[];
  reservePct: string;
  selectedCode: string;
  onSelect: (code: string) => void;
}) {
  const reserve = Math.max(Number(reservePct), 0);

  return (
    <div className="mt-4 space-y-3">
      <div className="flex h-4 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-900">
        {pods.map((pod) => {
          const width = Math.max(Number(pod.capital_allocation_pct), 0);
          if (width <= 0) return null;
          const selected = selectedCode === pod.code;

          return (
            <button
              key={pod.code}
              type="button"
              title={`${pod.name} · ${pct(pod.capital_allocation_pct)}`}
              style={{ width: `${width}%` }}
              onClick={() => onSelect(pod.code)}
              className={`transition hover:opacity-90 ${
                selected
                  ? "bg-zinc-800 dark:bg-zinc-200"
                  : "bg-zinc-500 dark:bg-zinc-500"
              }`}
            />
          );
        })}
        {reserve > 0 && (
          <div
            style={{ width: `${reserve}%` }}
            className="bg-zinc-200 dark:bg-zinc-700"
            title={`Reserve · ${pct(reservePct)}`}
          />
        )}
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-2">
        {pods.map((pod) => (
          <button
            key={pod.code}
            type="button"
            onClick={() => onSelect(pod.code)}
            className={`text-xs ${
              selectedCode === pod.code
                ? "font-semibold text-zinc-950 dark:text-zinc-100"
                : "text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300"
            }`}
          >
            {pod.name} · {pct(pod.capital_allocation_pct)}
          </button>
        ))}
        {reserve > 0 && (
          <span className="text-xs text-zinc-500">
            Reserve · {pct(reservePct)}
          </span>
        )}
      </div>
    </div>
  );
}

function OverviewPanel({ pod }: { pod: StrategyPod }) {
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
    <div className="space-y-6 px-5 py-5">
      <LifecycleStepper stage={pod.lifecycle_stage} />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Allocation" value={pct(pod.capital_allocation_pct)} />
        <MetricCard label="Risk budget" value={pct(pod.risk_budget_pct)} />
        <MetricCard label="Signal">
          <ScoreGauge value={pod.current_signal_score} />
        </MetricCard>
        <MetricCard label="Confidence">
          <ScoreGauge value={pod.model_confidence} />
        </MetricCard>
      </div>

      <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Mandate</p>
        <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">{pod.mandate}</p>
      </div>

      <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Allocation recommendation
            </p>
            <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
              {pod.allocation_recommendation}
            </p>
          </div>
          <StatusBadge label={formatLabel(pod.risk_level)} tone={riskTone(pod.risk_level)} />
        </div>
        <p className="mt-3 text-xs text-zinc-500">
          Current allocation: {pct(pod.capital_allocation_pct)} · Risk budget: {pct(pod.risk_budget_pct)}
        </p>
      </div>

      <div>
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

      <div>
        <p className="text-sm font-semibold">Model and gates</p>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
          <KeyValue label="Primary model" value={stringValue(currentSignals.primary_model)} />
          <KeyValue label="Primary question" value={stringValue(evaluation.primary_question)} />
          <KeyValue label="Required inputs" value={listValue(currentSignals.required_inputs)} />
          <KeyValue label="Minimum evidence" value={listValue(evaluation.minimum_evidence)} />
        </dl>
      </div>

      {evaluation.live && (
        <div>
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

function HistoryPanel({
  pod,
  snapshots,
  loading,
}: {
  pod: StrategyPod;
  snapshots: StrategyPodSnapshot[];
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="px-5 py-8 text-sm text-zinc-500">Loading snapshot history…</div>
    );
  }

  if (snapshots.length === 0) {
    return (
      <div className="px-5 py-8">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          No snapshots captured for {pod.name} yet.
        </p>
        <p className="mt-2 text-sm text-zinc-500">
          Use Capture snapshot to start an audit trail of signal, confidence, and allocation posture.
        </p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-zinc-200 bg-zinc-50/80 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900/50">
          <tr>
            <th className="px-5 py-3 font-medium">Captured</th>
            <th className="px-5 py-3 font-medium">As of</th>
            <th className="px-5 py-3 font-medium">Lifecycle</th>
            <th className="px-5 py-3 font-medium">Alloc</th>
            <th className="px-5 py-3 font-medium">Signal</th>
            <th className="px-5 py-3 font-medium">Confidence</th>
            <th className="px-5 py-3 font-medium">Risk</th>
            <th className="px-5 py-3 font-medium">Recommendation</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {snapshots.map((snapshot) => (
            <tr key={snapshot.snapshot_id}>
              <td className="px-5 py-4 whitespace-nowrap">
                {formatDate(snapshot.as_of_date)} · {formatTime(snapshot.captured_at)}
              </td>
              <td className="px-5 py-4">{formatDate(snapshot.as_of_date)}</td>
              <td className="px-5 py-4">{formatLabel(snapshot.lifecycle_stage)}</td>
              <td className="px-5 py-4 tabular-nums">{pct(snapshot.capital_allocation_pct)}</td>
              <td className="px-5 py-4">{scoreText(snapshot.current_signal_score)}</td>
              <td className="px-5 py-4">{scoreText(snapshot.model_confidence)}</td>
              <td className="px-5 py-4">
                <StatusBadge label={formatLabel(snapshot.risk_level)} tone={riskTone(snapshot.risk_level)} />
              </td>
              <td className="px-5 py-4 max-w-sm">
                <p className="line-clamp-2 text-zinc-600 dark:text-zinc-300">
                  {snapshot.allocation_recommendation}
                </p>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function GovernancePanel({ pod }: { pod: StrategyPod }) {
  return (
    <div className="space-y-6 px-5 py-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Approved instruments
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {pod.approved_instruments.length > 0 ? (
            pod.approved_instruments.map((instrument) => (
              <span
                key={instrument}
                className="rounded-md border border-zinc-200 px-2.5 py-1 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-300"
              >
                {instrument}
              </span>
            ))
          ) : (
            <p className="text-sm text-zinc-500">No approved instruments recorded.</p>
          )}
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Shutdown criteria
        </p>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {pod.shutdown_criteria ?? "No shutdown criteria recorded."}
        </p>
      </div>

      {pod.open_risk_warnings.length > 0 && (
        <div className="border-t border-zinc-200 pt-4 dark:border-zinc-800">
          <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">Risk warnings</p>
          <ul className="mt-2 space-y-1.5 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
            {pod.open_risk_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Latest snapshot
        </p>
        <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          {pod.latest_snapshot
            ? `${formatDate(pod.latest_snapshot.as_of_date)} at ${formatTime(pod.latest_snapshot.captured_at)}`
            : "No pod snapshot captured yet."}
        </p>
      </div>

      {pod.notes && (
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Notes</p>
          <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-300">{pod.notes}</p>
        </div>
      )}
    </div>
  );
}

function ControlsPanel({
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
    <form onSubmit={handleSubmit} className="space-y-6 px-5 py-5">
      <p className="text-sm text-zinc-500">
        Update pod controls deliberately. Monitoring lives on Overview; governance constraints are read-only on the Governance tab.
      </p>

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold">Status and lifecycle</legend>
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
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold">Capital and risk limits</legend>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Capital Allocation %">
            <input
              name="capital_allocation_pct"
              value={formState.capital_allocation_pct}
              onChange={(event) =>
                setFormStateValue(setFormState, "capital_allocation_pct", event.target.value)
              }
              className={inputClassName}
              inputMode="decimal"
            />
          </Field>
          <Field label="Risk Budget %">
            <input
              name="risk_budget_pct"
              value={formState.risk_budget_pct}
              onChange={(event) =>
                setFormStateValue(setFormState, "risk_budget_pct", event.target.value)
              }
              className={inputClassName}
              inputMode="decimal"
            />
          </Field>
          <Field label="Volatility Target %">
            <input
              name="volatility_target_pct"
              value={formState.volatility_target_pct}
              onChange={(event) =>
                setFormStateValue(setFormState, "volatility_target_pct", event.target.value)
              }
              className={inputClassName}
              inputMode="decimal"
            />
          </Field>
          <Field label="Max Drawdown %">
            <input
              name="max_drawdown_pct"
              value={formState.max_drawdown_pct}
              onChange={(event) =>
                setFormStateValue(setFormState, "max_drawdown_pct", event.target.value)
              }
              className={inputClassName}
              inputMode="decimal"
            />
          </Field>
          <Field label="Turnover Ceiling %">
            <input
              name="turnover_ceiling_pct"
              value={formState.turnover_ceiling_pct}
              onChange={(event) =>
                setFormStateValue(setFormState, "turnover_ceiling_pct", event.target.value)
              }
              className={inputClassName}
              inputMode="decimal"
            />
          </Field>
        </div>
      </fieldset>

      <fieldset className="space-y-4">
        <legend className="text-sm font-semibold">Mandate constraints</legend>
        <Field label="Approved Instruments">
          <textarea
            name="approved_instruments"
            value={formState.approved_instruments}
            onChange={(event) =>
              setFormStateValue(setFormState, "approved_instruments", event.target.value)
            }
            className={`${inputClassName} min-h-24 resize-y`}
            placeholder="Comma-separated list"
          />
        </Field>
        <Field label="Shutdown Criteria">
          <textarea
            name="shutdown_criteria"
            value={formState.shutdown_criteria}
            onChange={(event) =>
              setFormStateValue(setFormState, "shutdown_criteria", event.target.value)
            }
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
      </fieldset>

      <div className="flex justify-end">
        <button type="submit" disabled={saving} className={buttonPrimaryClassName}>
          {saving ? "Saving" : "Save controls"}
        </button>
      </div>
    </form>
  );
}

function LifecycleStepper({ stage }: { stage: string }) {
  const currentIndex = lifecycleOptions.indexOf(stage);

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Lifecycle</p>
      <div className="mt-3 flex flex-wrap gap-1">
        {lifecycleOptions.map((option, index) => {
          const active = option === stage;
          const complete = currentIndex >= 0 && index < currentIndex;

          return (
            <div
              key={option}
              className={`rounded-md px-2 py-1 text-[11px] font-medium ${
                active
                  ? "bg-zinc-950 text-white dark:bg-zinc-100 dark:text-zinc-950"
                  : complete
                    ? "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                    : "border border-zinc-200 text-zinc-400 dark:border-zinc-800"
              }`}
            >
              {formatLabel(option)}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScoreGauge({ value, compact = false }: { value: string | null; compact?: boolean }) {
  const score = parseScore(value);

  if (score === null) {
    return <span className="text-sm text-zinc-500">Pending</span>;
  }

  const width = Math.min(Math.max(score, 0), 100);

  return (
    <div className={compact ? "min-w-[88px]" : ""}>
      <div className="flex items-center gap-2">
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
          <div
            className="h-full rounded-full bg-zinc-600 dark:bg-zinc-400"
            style={{ width: `${width}%` }}
          />
        </div>
        {!compact && <span className="text-sm font-semibold tabular-nums">{score}/100</span>}
      </div>
      {compact && <p className="mt-1 text-xs font-semibold tabular-nums">{score}/100</p>}
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

function MetricCard({ label, value, children }: { label: string; value?: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</p>
      {value ? (
        <p className="mt-2 text-lg font-semibold tabular-nums">{value}</p>
      ) : (
        <div className="mt-2">{children}</div>
      )}
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

function recommendationAttention(recommendation: string): "action" | "hold" | "neutral" {
  const lower = recommendation.toLowerCase();
  if (
    lower.includes("halt") ||
    lower.includes("suspend") ||
    lower.includes("reduce") ||
    lower.includes("governance")
  ) {
    return "action";
  }
  if (lower.includes("hold") || lower.includes("maintain")) {
    return "hold";
  }
  return "neutral";
}

function parseScore(value: string | null) {
  if (value === null) return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function compareScores(left: string | null, right: string | null) {
  return (parseScore(left) ?? -1) - (parseScore(right) ?? -1);
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

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
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
  if (typeof value === "object") {
    return `${Object.keys(value).length} item${Object.keys(value).length === 1 ? "" : "s"}`;
  }
  return String(value);
}
