"use client";

import Link from "next/link";
import { FormEvent, useMemo, useState } from "react";
import { LoaderCover } from "@/components/ui/Loader";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import {
  createOpportunity,
  getOpportunityQueue,
  updateOpportunity,
  type Opportunity,
  type OpportunityCandidate,
  type OpportunityPriority,
  type OpportunityQueue as OpportunityQueueData,
  type OpportunityStatus,
  type OpportunityUpdateInput,
} from "@/lib/api";
import { tickerHubPath } from "@/lib/ticker-hub-path";

type OpportunityQueueProps = {
  queue: OpportunityQueueData | null;
  isUnavailable: boolean;
};

const PAGE_SIZE = 20;

const statusLabels: Record<OpportunityStatus, string> = {
  discovered: "Discovered",
  screening: "Screening",
  research: "Research",
  parked: "Parked",
  candidate: "Candidate",
  approved: "Approved",
  active_position: "Active Position",
  exited: "Exited",
  post_mortem: "Post-Mortem",
  rejected: "Rejected",
};

const priorityLabels: Record<OpportunityPriority, string> = {
  low: "Low",
  medium: "Medium",
  high: "High",
  urgent: "Urgent",
};

const nextStatusByStatus: Partial<Record<OpportunityStatus, OpportunityStatus>> = {
  discovered: "screening",
  screening: "research",
  research: "candidate",
  parked: "candidate",
  candidate: "approved",
  approved: "active_position",
  active_position: "exited",
  exited: "post_mortem",
};

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const money = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 2,
});

export function OpportunityQueue({
  queue: initialQueue,
  isUnavailable,
}: OpportunityQueueProps) {
  const [queue, setQueue] = useState(initialQueue);
  const [selectedId, setSelectedId] = useState(initialQueue?.opportunities[0]?.id ?? "");
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | "all">("all");
  const [page, setPage] = useState(initialQueue?.page ?? 1);
  const [listLoading, setListLoading] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const [showManualCreate, setShowManualCreate] = useState(false);
  const [showEdit, setShowEdit] = useState(false);

  const opportunities = useMemo(() => queue?.opportunities ?? [], [queue?.opportunities]);
  const selectedOpportunity =
    opportunities.find((opportunity) => opportunity.id === selectedId) ??
    opportunities[0] ??
    null;
  const strategyPods = queue?.strategy_pods ?? [];

  async function reloadQueue(nextPage = page, nextStatus = statusFilter) {
    const nextQueue = await getOpportunityQueue({
      page: nextPage,
      page_size: PAGE_SIZE,
      status: nextStatus,
    });
    setQueue(nextQueue);
    setPage(nextQueue.page);
    setSelectedId((current) => {
      if (nextQueue.opportunities.some((opportunity) => opportunity.id === current)) {
        return current;
      }
      return nextQueue.opportunities[0]?.id ?? "";
    });
    return nextQueue;
  }

  async function handleStatusFilter(next: OpportunityStatus | "all") {
    setStatusFilter(next);
    setListLoading(true);
    try {
      await reloadQueue(1, next);
    } catch {
      toast.error("Queue could not reload.");
    } finally {
      setListLoading(false);
    }
  }

  async function handlePageChange(nextPage: number) {
    setListLoading(true);
    try {
      await reloadQueue(nextPage, statusFilter);
    } catch {
      toast.error("Queue could not reload.");
    } finally {
      setListLoading(false);
    }
  }

  async function handleCreateFromCandidate(candidate: OpportunityCandidate) {
    setPending(candidate.memo_id);
    try {
      const composite = Number(candidate.composite_score ?? 0);
      const created = await createOpportunity({
        source_memo_id: candidate.memo_id,
        strategy_pod_code: candidate.suggested_strategy_pod_code ?? "fundamental_equity",
        status: "screening",
        priority: composite >= 75 ? "high" : "medium",
      });
      setStatusFilter(created.status);
      await reloadQueue(1, created.status);
      setSelectedId(created.id);
      setShowCandidates(false);
      toast.success(`${candidate.ticker} moved into the opportunity queue.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Opportunity could not be created.");
    } finally {
      setPending(null);
    }
  }

  async function handleManualCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const ticker = textValue(formData, "ticker").toUpperCase();
    const thesis = textValue(formData, "thesis");
    if (!ticker || !thesis) {
      toast.error("Ticker and thesis are required.");
      return;
    }

    setPending("manual-create");
    try {
      const created = await createOpportunity({
        instrument: {
          ticker,
          name: textValue(formData, "name") || ticker,
          asset_class: String(formData.get("asset_class") ?? "equity") as
            | "equity"
            | "etf"
            | "bond"
            | "commodity"
            | "cash_equivalent"
            | "other",
          exchange: textValue(formData, "exchange") || undefined,
          currency: textValue(formData, "currency") || "USD",
          sector: textValue(formData, "sector") || undefined,
        },
        strategy_pod_code: textValue(formData, "strategy_pod_code") || undefined,
        status: String(formData.get("status") ?? "screening") as OpportunityStatus,
        priority: String(formData.get("priority") ?? "medium") as OpportunityPriority,
        thesis,
        research_question: textValue(formData, "research_question") || undefined,
        target_weight: textValue(formData, "target_weight") || undefined,
        review_by: textValue(formData, "review_by") || undefined,
        notes: textValue(formData, "notes") || undefined,
      });
      setStatusFilter(created.status);
      await reloadQueue(1, created.status);
      setSelectedId(created.id);
      setShowManualCreate(false);
      toast.success(`${ticker} added to the opportunity queue.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Opportunity could not be created.");
    } finally {
      setPending(null);
    }
  }

  async function patchOpportunity(
    opportunity: Opportunity,
    payload: OpportunityUpdateInput,
    successMessage: string,
  ) {
    setPending(opportunity.id);
    try {
      const updated = await updateOpportunity(opportunity.id, payload);
      const statusChanged = payload.status && payload.status !== opportunity.status;
      const nextStatus = statusChanged ? updated.status : statusFilter;
      const nextPage = statusChanged ? 1 : page;
      if (nextStatus !== statusFilter) setStatusFilter(nextStatus);
      await reloadQueue(nextPage, nextStatus);
      setSelectedId(updated.id);
      toast.success(successMessage);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Opportunity could not be updated.");
    } finally {
      setPending(null);
    }
  }

  async function handleUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedOpportunity) return;

    const formData = new FormData(event.currentTarget);
    const payload: OpportunityUpdateInput = {
      status: String(formData.get("status") ?? selectedOpportunity.status) as OpportunityStatus,
      priority: String(
        formData.get("priority") ?? selectedOpportunity.priority,
      ) as OpportunityPriority,
      strategy_pod_code: textValue(formData, "strategy_pod_code") || undefined,
      thesis: textValue(formData, "thesis"),
      research_question: textValue(formData, "research_question"),
      next_action: textValue(formData, "next_action"),
      target_weight: textValue(formData, "target_weight") || undefined,
      review_by: textValue(formData, "review_by") || undefined,
      notes: textValue(formData, "notes"),
      override_reason: textValue(formData, "override_reason") || undefined,
      entry_zone: textValue(formData, "entry_zone") || undefined,
      invalidation: textValue(formData, "invalidation") || undefined,
      max_loss_pct_nav: textValue(formData, "max_loss_pct_nav") || undefined,
      time_stop_sessions: numberValue(formData, "time_stop_sessions"),
      thesis_breaker: textValue(formData, "thesis_breaker") || undefined,
    };
    const preTradeInput = textValue(formData, "pre_trade_check_id");
    if (preTradeInput || selectedOpportunity.pre_trade_risk_check_id) {
      payload.pre_trade_check_id = preTradeInput || null;
    }

    setPending(selectedOpportunity.id);
    try {
      const updated = await updateOpportunity(selectedOpportunity.id, payload);
      const statusChanged =
        payload.status && payload.status !== selectedOpportunity.status;
      const nextStatus = statusChanged ? updated.status : statusFilter;
      const nextPage = statusChanged ? 1 : page;
      if (nextStatus !== statusFilter) setStatusFilter(nextStatus);
      await reloadQueue(nextPage, nextStatus);
      setSelectedId(updated.id);
      setShowEdit(false);
      toast.success(`${selectedOpportunity.instrument.ticker} opportunity updated.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Opportunity could not be updated.");
    } finally {
      setPending(null);
    }
  }

  if (!queue) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {isUnavailable
          ? "Opportunity queue could not be loaded yet. Sign in again or refresh this page."
          : "No opportunity queue is available yet."}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Research pipeline
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Opportunity Queue</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Tracks where each name sits in the investment process. Parked is not the radar
              watchlist.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setShowManualCreate((current) => !current)}
              className={buttonSecondaryClassName}
            >
              {showManualCreate ? "Close manual add" : "Add manually"}
            </button>
            <button
              type="button"
              onClick={() => setShowCandidates((current) => !current)}
              className={buttonSecondaryClassName}
            >
              {showCandidates
                ? "Hide candidates"
                : `Candidates (${queue.summary.candidates})`}
            </button>
          </div>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-4 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
          <Metric label="Active" value={String(queue.summary.active)} />
          <Metric label="High priority" value={String(queue.summary.high_priority)} />
          <Metric label="Approved" value={String(queue.summary.approved)} />
          <Metric
            label="Next review"
            value={
              queue.summary.next_review_by ? formatDate(queue.summary.next_review_by) : "—"
            }
          />
        </div>
        <StatusRail
          queue={queue}
          value={statusFilter}
          disabled={listLoading}
          onChange={handleStatusFilter}
        />
      </section>

      {showManualCreate && (
        <ManualOpportunityForm
          pending={pending === "manual-create"}
          statusOrder={queue.status_order}
          strategyPods={strategyPods}
          onSubmit={handleManualCreate}
        />
      )}

      {showCandidates && (
        <CandidateList
          candidates={queue.candidates}
          pendingId={pending}
          onAdd={handleCreateFromCandidate}
        />
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(300px,380px)_1fr]">
        <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex items-center justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
            <div>
              <h3 className="text-sm font-semibold">Queue</h3>
              <p className="mt-0.5 text-xs text-zinc-500">
                {statusFilter === "all" ? "All statuses" : statusLabels[statusFilter]}
              </p>
            </div>
            {statusFilter !== "all" && (
              <button
                type="button"
                onClick={() => void handleStatusFilter("all")}
                disabled={listLoading}
                className={buttonSecondaryClassName}
              >
                Clear
              </button>
            )}
          </div>

          <div className="relative min-h-48">
            {listLoading ? <LoaderCover label="Loading queue" /> : null}
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {opportunities.map((opportunity) => {
                const selected = opportunity.id === selectedOpportunity?.id;
                return (
                  <li key={opportunity.id}>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedId(opportunity.id);
                        setShowEdit(false);
                      }}
                      className={`flex w-full items-start justify-between gap-3 px-4 py-3 text-left transition ${
                        selected
                          ? "bg-zinc-100 dark:bg-zinc-900"
                          : "hover:bg-zinc-50 dark:hover:bg-zinc-900/50"
                      }`}
                    >
                      <div className="min-w-0">
                        <p className="font-medium">{opportunity.instrument.ticker}</p>
                        <p className="mt-0.5 truncate text-xs text-zinc-500">
                          {opportunity.strategy_pod?.name ?? "Unassigned"} ·{" "}
                          {priorityLabels[opportunity.priority]}
                        </p>
                      </div>
                      <StatusPill status={opportunity.status} />
                    </button>
                  </li>
                );
              })}
              {opportunities.length === 0 && (
                <li className="px-4 py-10 text-center text-sm text-zinc-500">
                  No opportunities match this filter.
                </li>
              )}
            </ul>
          </div>

          {queue.total > 0 && (
            <div className="flex items-center justify-between gap-2 border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
              <p className="text-xs text-zinc-500">
                {queue.total} total · page {queue.page}/{queue.total_pages}
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => void handlePageChange(page - 1)}
                  disabled={listLoading || page <= 1}
                  className={buttonSecondaryClassName}
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() => void handlePageChange(page + 1)}
                  disabled={listLoading || page >= queue.total_pages}
                  className={buttonSecondaryClassName}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </section>

        {selectedOpportunity ? (
          <OpportunityDetail
            opportunity={selectedOpportunity}
            pending={pending === selectedOpportunity.id}
            statusOrder={queue.status_order}
            strategyPods={strategyPods}
            showEdit={showEdit}
            onToggleEdit={() => setShowEdit((current) => !current)}
            onSubmit={handleUpdate}
            onPatch={patchOpportunity}
          />
        ) : (
          <section className="flex items-center justify-center rounded-xl border border-dashed border-zinc-300 px-5 py-16 text-sm text-zinc-500 dark:border-zinc-700">
            Select an opportunity to inspect.
          </section>
        )}
      </div>
    </div>
  );
}

function StatusRail({
  queue,
  value,
  disabled,
  onChange,
}: {
  queue: OpportunityQueueData;
  value: OpportunityStatus | "all";
  disabled: boolean;
  onChange: (status: OpportunityStatus | "all") => void;
}) {
  const allSelected = value === "all";
  return (
    <div className="flex gap-2 overflow-x-auto border-t border-zinc-200 px-5 py-3 dark:border-zinc-800">
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange("all")}
        className={`shrink-0 rounded-md border px-3 py-2 text-left text-xs transition ${
          allSelected
            ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-950"
            : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
        }`}
      >
        <span className="block font-medium">All</span>
        <span className="tabular-nums opacity-75">{queue.summary.total}</span>
      </button>
      {queue.status_order.map((status) => {
        const selected = value === status;
        const count = queue.summary.status_counts[status] ?? 0;
        return (
          <button
            key={status}
            type="button"
            disabled={disabled}
            onClick={() => onChange(status)}
            className={`shrink-0 rounded-md border px-3 py-2 text-left text-xs transition ${
              selected
                ? "border-zinc-900 bg-zinc-900 text-white dark:border-white dark:bg-white dark:text-zinc-950"
                : "border-zinc-200 bg-white text-zinc-700 hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900"
            }`}
          >
            <span className="block font-medium">{statusLabels[status]}</span>
            <span className="tabular-nums opacity-75">{count}</span>
          </button>
        );
      })}
    </div>
  );
}

function ManualOpportunityForm({
  pending,
  statusOrder,
  strategyPods,
  onSubmit,
}: {
  pending: boolean;
  statusOrder: OpportunityStatus[];
  strategyPods: NonNullable<OpportunityQueueData["strategy_pods"]>;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <form className="space-y-4 px-5 py-5" onSubmit={onSubmit}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Manual opportunity</h3>
            <p className="mt-1 text-sm text-zinc-500">Add a name before a memo exists.</p>
          </div>
          <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
            {pending ? "Adding…" : "Add opportunity"}
          </button>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Ticker">
            <input name="ticker" className={inputClassName} required />
          </Field>
          <Field label="Name">
            <input name="name" className={inputClassName} />
          </Field>
          <Field label="Asset class">
            <select name="asset_class" defaultValue="equity" className={inputClassName}>
              <option value="equity">Equity</option>
              <option value="etf">ETF</option>
              <option value="bond">Bond</option>
              <option value="commodity">Commodity</option>
              <option value="cash_equivalent">Cash equivalent</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Exchange">
            <input name="exchange" className={inputClassName} placeholder="NASDAQ" />
          </Field>
          <Field label="Currency">
            <input name="currency" defaultValue="USD" className={inputClassName} />
          </Field>
          <Field label="Sector">
            <input name="sector" className={inputClassName} />
          </Field>
          <Field label="Status">
            <select name="status" defaultValue="screening" className={inputClassName}>
              {statusOrder.map((status) => (
                <option key={status} value={status}>
                  {statusLabels[status]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Priority">
            <select name="priority" defaultValue="medium" className={inputClassName}>
              {(Object.keys(priorityLabels) as OpportunityPriority[]).map((priority) => (
                <option key={priority} value={priority}>
                  {priorityLabels[priority]}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Strategy pod">
            <select
              name="strategy_pod_code"
              defaultValue="fundamental_equity"
              className={inputClassName}
            >
              {strategyPods.map((pod) => (
                <option key={pod.code} value={pod.code}>
                  {pod.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Target weight %">
            <input name="target_weight" className={inputClassName} inputMode="decimal" />
          </Field>
          <Field label="Review by">
            <input name="review_by" type="date" className={inputClassName} />
          </Field>
        </div>
        <Field label="Thesis">
          <textarea
            name="thesis"
            className={`${inputClassName} min-h-20 resize-y`}
            required
          />
        </Field>
        <Field label="Research question">
          <textarea
            name="research_question"
            className={`${inputClassName} min-h-16 resize-y`}
          />
        </Field>
        <Field label="Notes">
          <textarea name="notes" className={`${inputClassName} min-h-16 resize-y`} />
        </Field>
      </form>
    </section>
  );
}

function CandidateList({
  candidates,
  pendingId,
  onAdd,
}: {
  candidates: OpportunityCandidate[];
  pendingId: string | null;
  onAdd: (candidate: OpportunityCandidate) => void;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">Research candidates</h3>
        <p className="mt-1 text-sm text-zinc-500">Recent ticker memos not yet queued</p>
      </div>
      <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
        {candidates.map((candidate) => (
          <div
            key={candidate.memo_id}
            className="flex flex-wrap items-start justify-between gap-4 px-5 py-4"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <p className="font-medium">{candidate.ticker}</p>
                <span className="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400">
                  {candidate.classification}
                </span>
              </div>
              <p className="mt-1 text-sm text-zinc-500">{candidate.executive_view}</p>
            </div>
            <button
              type="button"
              onClick={() => onAdd(candidate)}
              disabled={pendingId === candidate.memo_id}
              className={buttonSecondaryClassName}
            >
              {pendingId === candidate.memo_id ? "Adding…" : "Add"}
            </button>
          </div>
        ))}
        {candidates.length === 0 && (
          <p className="px-5 py-8 text-sm text-zinc-500">No unqueued memos yet.</p>
        )}
      </div>
    </section>
  );
}

function OpportunityDetail({
  opportunity,
  pending,
  statusOrder,
  strategyPods,
  showEdit,
  onToggleEdit,
  onSubmit,
  onPatch,
}: {
  opportunity: Opportunity;
  pending: boolean;
  statusOrder: OpportunityStatus[];
  strategyPods: NonNullable<OpportunityQueueData["strategy_pods"]>;
  showEdit: boolean;
  onToggleEdit: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onPatch: (
    opportunity: Opportunity,
    payload: OpportunityUpdateInput,
    successMessage: string,
  ) => void;
}) {
  const links = opportunity.links;
  const ticker = opportunity.instrument.ticker;
  const nextStatus = nextStatusByStatus[opportunity.status];
  const latestUnlinkedCheck =
    links.pre_trade && !links.pre_trade.linked ? links.pre_trade : null;

  return (
    <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPill status={opportunity.status} />
              <span className="rounded-md bg-zinc-100 px-2 py-0.5 text-[11px] font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
                {priorityLabels[opportunity.priority]}
              </span>
            </div>
            <h3 className="mt-2 text-lg font-semibold">{ticker}</h3>
            <p className="mt-1 text-sm text-zinc-500">{opportunity.instrument.name}</p>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
              {opportunity.strategy_pod?.name ?? "No strategy pod assigned"}
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            {latestUnlinkedCheck && (
              <button
                type="button"
                onClick={() =>
                  onPatch(
                    opportunity,
                    { pre_trade_check_id: latestUnlinkedCheck.id },
                    `${ticker} pre-trade check linked.`,
                  )
                }
                disabled={pending}
                className={buttonSecondaryClassName}
              >
                Link risk check
              </button>
            )}
            {nextStatus && (
              <button
                type="button"
                onClick={() =>
                  onPatch(
                    opportunity,
                    { status: nextStatus },
                    `${ticker} moved to ${statusLabels[nextStatus]}.`,
                  )
                }
                disabled={pending}
                className={buttonPrimaryClassName}
              >
                Move to {statusLabels[nextStatus]}
              </button>
            )}
            <button type="button" onClick={onToggleEdit} className={buttonSecondaryClassName}>
              {showEdit ? "Close" : "Edit"}
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3 text-sm">
          <Link
            href={tickerHubPath(ticker)}
            className="text-zinc-700 underline-offset-4 hover:underline dark:text-zinc-300"
          >
            Ticker hub
          </Link>
          <Link
            href={`/ticker-analyst?analyze=${encodeURIComponent(ticker)}&workflow=1`}
            className="text-zinc-700 underline-offset-4 hover:underline dark:text-zinc-300"
          >
            Analyst
          </Link>
          <Link
            href={`/risk-centre?ticker=${encodeURIComponent(ticker)}`}
            className="text-zinc-700 underline-offset-4 hover:underline dark:text-zinc-300"
          >
            Risk
          </Link>
          <Link
            href="/trade-journal"
            className="text-zinc-700 underline-offset-4 hover:underline dark:text-zinc-300"
          >
            Trade Journal
          </Link>
        </div>
      </div>

      <div className="space-y-5 px-5 py-5">
        <div className="flex flex-wrap gap-2">
          {opportunity.status !== "parked" && (
            <button
              type="button"
              onClick={() =>
                onPatch(opportunity, { status: "parked" }, `${ticker} parked.`)
              }
              disabled={pending}
              className={buttonSecondaryClassName}
            >
              Park
            </button>
          )}
          {opportunity.status !== "rejected" && (
            <button
              type="button"
              onClick={() =>
                onPatch(opportunity, { status: "rejected" }, `${ticker} rejected.`)
              }
              disabled={pending}
              className={buttonSecondaryClassName}
            >
              Reject
            </button>
          )}
        </div>

        <div className="rounded-lg border border-zinc-200 bg-zinc-50/80 px-4 py-3 dark:border-zinc-800 dark:bg-zinc-900/40">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Next action
          </p>
          <p className="mt-1 text-sm leading-6 text-zinc-800 dark:text-zinc-200">
            {opportunity.next_action || "No next action set."}
          </p>
        </div>

        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <Brief
            label="Memo"
            value={
              links.memo
                ? `${links.memo.classification} · ${formatDate(links.memo.memo_date)}`
                : "None yet"
            }
          />
          <Brief
            label="Pre-trade"
            value={
              links.pre_trade
                ? `${links.pre_trade.decision} · ${links.pre_trade.risk_level}${
                    links.pre_trade.linked ? "" : " · not linked"
                  }`
                : "Not run"
            }
          />
          <Brief
            label="Position"
            value={
              links.position
                ? `${links.position.quantity} @ ${money.format(Number(links.position.average_cost))}`
                : "No live position"
            }
          />
          <Brief
            label="Review by"
            value={opportunity.review_by ? formatDate(opportunity.review_by) : "—"}
          />
        </dl>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Thesis</p>
          <p className="mt-2 text-sm leading-6 text-zinc-700 dark:text-zinc-300">
            {opportunity.thesis || "No thesis yet."}
          </p>
        </div>

        {links.blockers.length > 0 && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            <p className="font-medium">Next status needs</p>
            <ul className="mt-1 list-disc pl-4">
              {links.blockers.map((blocker) => (
                <li key={blocker}>{blocker}</li>
              ))}
            </ul>
          </div>
        )}

        {opportunity.discovery_evidence &&
        Object.keys(opportunity.discovery_evidence).length > 0 ? (
          <DiscoveryEvidence evidence={opportunity.discovery_evidence} />
        ) : null}

        {showEdit && (
          <form
            key={`${opportunity.id}-${opportunity.updated_at}`}
            className="space-y-4 border-t border-zinc-200 pt-5 dark:border-zinc-800"
            onSubmit={onSubmit}
          >
            <p className="text-sm font-semibold">Edit opportunity</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Status">
                <select
                  name="status"
                  defaultValue={opportunity.status}
                  className={inputClassName}
                >
                  {statusOrder.map((status) => (
                    <option key={status} value={status}>
                      {statusLabels[status]}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Priority">
                <select
                  name="priority"
                  defaultValue={opportunity.priority}
                  className={inputClassName}
                >
                  {(Object.keys(priorityLabels) as OpportunityPriority[]).map((priority) => (
                    <option key={priority} value={priority}>
                      {priorityLabels[priority]}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Strategy pod">
                <select
                  name="strategy_pod_code"
                  defaultValue={opportunity.strategy_pod?.code ?? "fundamental_equity"}
                  className={inputClassName}
                >
                  {strategyPods.map((pod) => (
                    <option key={pod.code} value={pod.code}>
                      {pod.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Target weight %">
                <input
                  name="target_weight"
                  defaultValue={opportunity.target_weight ?? ""}
                  className={inputClassName}
                  inputMode="decimal"
                />
              </Field>
              <Field label="Review by">
                <input
                  name="review_by"
                  type="date"
                  defaultValue={opportunity.review_by ?? ""}
                  className={inputClassName}
                />
              </Field>
              <Field label="Pre-trade check ID">
                <input
                  name="pre_trade_check_id"
                  defaultValue={
                    opportunity.pre_trade_risk_check_id ??
                    (latestUnlinkedCheck ? latestUnlinkedCheck.id : "")
                  }
                  className={inputClassName}
                  placeholder="Paste or keep the latest matching check"
                />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Entry zone">
                <input
                  name="entry_zone"
                  defaultValue={entryPlanValue(opportunity, "entry_zone")}
                  className={inputClassName}
                  placeholder="Required for Candidate / Approved"
                />
              </Field>
              <Field label="Invalidation / stop">
                <input
                  name="invalidation"
                  defaultValue={entryPlanValue(opportunity, "invalidation")}
                  className={inputClassName}
                  placeholder="Required for Candidate / Approved"
                />
              </Field>
              <Field label="Max loss % NAV">
                <input
                  name="max_loss_pct_nav"
                  defaultValue={entryPlanValue(opportunity, "max_loss_pct_nav")}
                  className={inputClassName}
                  inputMode="decimal"
                />
              </Field>
              <Field label="Time stop (sessions)">
                <input
                  name="time_stop_sessions"
                  type="number"
                  min={1}
                  max={90}
                  defaultValue={entryPlanValue(opportunity, "time_stop_sessions")}
                  className={inputClassName}
                />
              </Field>
            </div>
            <Field label="Thesis breaker">
              <input
                name="thesis_breaker"
                defaultValue={entryPlanValue(opportunity, "thesis_breaker")}
                className={inputClassName}
                placeholder="What kills the idea regardless of price?"
              />
            </Field>
            <Field label="Thesis">
              <textarea
                name="thesis"
                defaultValue={opportunity.thesis}
                className={`${inputClassName} min-h-24 resize-y`}
              />
            </Field>
            <Field label="Research question">
              <textarea
                name="research_question"
                defaultValue={opportunity.research_question ?? ""}
                className={`${inputClassName} min-h-20 resize-y`}
              />
            </Field>
            <Field label="Next action">
              <textarea
                name="next_action"
                defaultValue={opportunity.next_action ?? ""}
                className={`${inputClassName} min-h-16 resize-y`}
              />
            </Field>
            <Field label="Notes">
              <textarea
                name="notes"
                defaultValue={opportunity.notes ?? ""}
                className={`${inputClassName} min-h-16 resize-y`}
              />
            </Field>
            <Field label="Override reason">
              <input
                name="override_reason"
                className={inputClassName}
                placeholder="Required only when skipping a status gate"
              />
            </Field>
            <div className="flex justify-end">
              <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
                {pending ? "Saving…" : "Save changes"}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

function DiscoveryEvidence({ evidence }: { evidence: Record<string, unknown> }) {
  const entries = Object.entries(evidence).slice(0, 6);
  if (entries.length === 0) return null;
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        Discovery evidence
      </p>
      <dl className="mt-2 grid gap-2 text-sm sm:grid-cols-2">
        {entries.map(([key, value]) => (
          <div key={key}>
            <dt className="text-xs uppercase tracking-wide text-zinc-500">
              {key.replaceAll("_", " ")}
            </dt>
            <dd className="mt-0.5 text-zinc-700 dark:text-zinc-300">
              {typeof value === "object" ? JSON.stringify(value) : String(value)}
            </dd>
          </div>
        ))}
      </dl>
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

function Brief({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="mt-1 text-zinc-700 dark:text-zinc-300">{value}</dd>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      <span className="mb-1.5 block">{label}</span>
      {children}
    </label>
  );
}

function StatusPill({ status }: { status: OpportunityStatus }) {
  const tone =
    status === "approved" || status === "active_position"
      ? "good"
      : status === "rejected" || status === "exited"
        ? "bad"
        : status === "candidate" || status === "research"
          ? "warn"
          : "neutral";
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
      {statusLabels[status]}
    </span>
  );
}

function textValue(formData: FormData, key: string) {
  const value = formData.get(key);
  if (typeof value !== "string") return "";
  return value.trim();
}

function numberValue(formData: FormData, key: string): number | undefined {
  const raw = textValue(formData, key);
  if (!raw) return undefined;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function entryPlanValue(opportunity: Opportunity, key: string): string {
  const evidence = opportunity.discovery_evidence || {};
  const plan = evidence.entry_plan;
  if (!plan || typeof plan !== "object" || Array.isArray(plan)) return "";
  const value = (plan as Record<string, unknown>)[key];
  return value == null ? "" : String(value);
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}
