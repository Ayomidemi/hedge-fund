"use client";

import { FormEvent, useMemo, useState } from "react";
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

type OpportunityQueueProps = {
  queue: OpportunityQueueData | null;
  isUnavailable: boolean;
};

const statusLabels: Record<OpportunityStatus, string> = {
  discovered: "Discovered",
  screening: "Screening",
  research: "Research",
  watchlist: "Watchlist",
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

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function OpportunityQueue({
  queue: initialQueue,
  isUnavailable,
}: OpportunityQueueProps) {
  const [queue, setQueue] = useState(initialQueue);
  const [selectedId, setSelectedId] = useState(initialQueue?.opportunities[0]?.id ?? "");
  const [statusFilter, setStatusFilter] = useState<OpportunityStatus | "all">("all");
  const [pending, setPending] = useState<string | null>(null);

  const opportunities = useMemo(() => queue?.opportunities ?? [], [queue?.opportunities]);
  const filteredOpportunities = useMemo(() => {
    if (statusFilter === "all") return opportunities;
    return opportunities.filter((opportunity) => opportunity.status === statusFilter);
  }, [opportunities, statusFilter]);

  const selectedOpportunity =
    filteredOpportunities.find((opportunity) => opportunity.id === selectedId) ??
    filteredOpportunities[0] ??
    null;

  async function reloadQueue() {
    const nextQueue = await getOpportunityQueue();
    setQueue(nextQueue);
    setSelectedId((current) => {
      if (nextQueue.opportunities.some((opportunity) => opportunity.id === current)) {
        return current;
      }
      return nextQueue.opportunities[0]?.id ?? "";
    });
    return nextQueue;
  }

  async function handleCreateFromCandidate(candidate: OpportunityCandidate) {
    setPending(candidate.memo_id);
    try {
      const composite = Number(candidate.composite_score ?? 0);
      await createOpportunity({
        source_memo_id: candidate.memo_id,
        status: "screening",
        priority: composite >= 75 ? "high" : "medium",
      });
      const nextQueue = await reloadQueue();
      const created = nextQueue.opportunities.find(
        (opportunity) => opportunity.source_memo_id === candidate.memo_id,
      );
      setSelectedId(created?.id ?? nextQueue.opportunities[0]?.id ?? "");
      toast.success(`${candidate.ticker} moved into the opportunity queue.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Opportunity could not be created.");
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
      thesis: textValue(formData, "thesis"),
      research_question: textValue(formData, "research_question"),
      next_action: textValue(formData, "next_action"),
      review_by: textValue(formData, "review_by") || undefined,
      notes: textValue(formData, "notes"),
    };

    setPending(selectedOpportunity.id);
    try {
      const updated = await updateOpportunity(selectedOpportunity.id, payload);
      setQueue((current) =>
        current
          ? {
              ...current,
              opportunities: current.opportunities.map((opportunity) =>
                opportunity.id === updated.id ? updated : opportunity,
              ),
            }
          : current,
      );
      toast.success(`${updated.instrument.ticker} opportunity updated.`);
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

  const metrics = [
    { label: "Active", value: String(queue.summary.active) },
    { label: "High priority", value: String(queue.summary.high_priority) },
    { label: "Approved", value: String(queue.summary.approved) },
    { label: "Candidates", value: String(queue.summary.candidates) },
    {
      label: "Next review",
      value: queue.summary.next_review_by ? formatDate(queue.summary.next_review_by) : "-",
    },
  ];

  return (
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            Research pipeline
          </p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight">Opportunity Queue</h2>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-5 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
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

      <section className="grid gap-5 xl:grid-cols-[1.25fr_0.75fr]">
        <div className="flex min-w-0 flex-col gap-5">
          <QueueTable
            opportunities={filteredOpportunities}
            selectedId={selectedOpportunity?.id ?? ""}
            statusFilter={statusFilter}
            statusOrder={queue.status_order}
            onSelect={setSelectedId}
            onStatusFilter={setStatusFilter}
          />
          <CandidateList
            candidates={queue.candidates}
            pendingId={pending}
            onAdd={handleCreateFromCandidate}
          />
        </div>

        <OpportunityDetail
          opportunity={selectedOpportunity}
          pending={pending === selectedOpportunity?.id}
          statusOrder={queue.status_order}
          onSubmit={handleUpdate}
        />
      </section>
    </div>
  );
}

function QueueTable({
  opportunities,
  selectedId,
  statusFilter,
  statusOrder,
  onSelect,
  onStatusFilter,
}: {
  opportunities: Opportunity[];
  selectedId: string;
  statusFilter: OpportunityStatus | "all";
  statusOrder: OpportunityStatus[];
  onSelect: (id: string) => void;
  onStatusFilter: (status: OpportunityStatus | "all") => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div>
          <h3 className="text-sm font-semibold">Queue</h3>
          <p className="mt-1 text-sm text-zinc-500">
            {opportunities.length} opportunity{opportunities.length === 1 ? "" : "ies"}
          </p>
        </div>
        <select
          value={statusFilter}
          onChange={(event) =>
            onStatusFilter(event.target.value as OpportunityStatus | "all")
          }
          className={`${inputClassName} mt-0 h-10 w-44`}
        >
          <option value="all">All statuses</option>
          {statusOrder.map((status) => (
            <option key={status} value={status}>
              {statusLabels[status]}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>Ticker</Th>
              <Th>Status</Th>
              <Th>Priority</Th>
              <Th>Action</Th>
              <Th>Score</Th>
              <Th>Review</Th>
            </tr>
          </thead>
          <tbody>
            {opportunities.map((opportunity) => (
              <tr
                key={opportunity.id}
                onClick={() => onSelect(opportunity.id)}
                className={`cursor-pointer border-b border-zinc-100 transition last:border-0 dark:border-zinc-900 ${
                  opportunity.id === selectedId
                    ? "bg-zinc-100 dark:bg-zinc-900"
                    : "hover:bg-zinc-50 dark:hover:bg-zinc-900/60"
                }`}
              >
                <Td emphasis>{opportunity.instrument.ticker}</Td>
                <Td>
                  <StatusPill status={opportunity.status} />
                </Td>
                <Td>{priorityLabels[opportunity.priority]}</Td>
                <Td>{opportunity.latest_action ?? "-"}</Td>
                <Td>{opportunity.latest_composite_score ?? "-"}</Td>
                <Td>{opportunity.review_by ? formatDate(opportunity.review_by) : "-"}</Td>
              </tr>
            ))}
            {opportunities.length === 0 && (
              <tr>
                <td colSpan={6} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No opportunities match this filter.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
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
    <div className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
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
              {pendingId === candidate.memo_id ? "Adding..." : "Add"}
            </button>
          </div>
        ))}
        {candidates.length === 0 && (
          <p className="px-5 py-8 text-sm text-zinc-500">No unqueued memos yet.</p>
        )}
      </div>
    </div>
  );
}

function OpportunityDetail({
  opportunity,
  pending,
  statusOrder,
  onSubmit,
}: {
  opportunity: Opportunity | null;
  pending: boolean;
  statusOrder: OpportunityStatus[];
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  if (!opportunity) {
    return (
      <aside className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-sm text-zinc-500">Select an opportunity to manage it.</p>
      </aside>
    );
  }

  return (
    <aside className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
          {opportunity.instrument.asset_class}
        </p>
        <h3 className="mt-1 text-xl font-semibold tracking-tight">
          {opportunity.instrument.ticker}
        </h3>
        <p className="mt-1 text-sm text-zinc-500">{opportunity.instrument.name}</p>
      </div>

      <form key={opportunity.id} className="mt-5 space-y-4" onSubmit={onSubmit}>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <Field label="Status">
            <select name="status" defaultValue={opportunity.status} className={inputClassName}>
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
              {Object.entries(priorityLabels).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
        </div>

        <Field label="Review by">
          <input
            name="review_by"
            type="date"
            defaultValue={opportunity.review_by ?? ""}
            className={inputClassName}
          />
        </Field>

        <Field label="Research question">
          <textarea
            name="research_question"
            rows={3}
            defaultValue={opportunity.research_question ?? ""}
            className={inputClassName}
          />
        </Field>

        <Field label="Thesis">
          <textarea
            name="thesis"
            rows={4}
            defaultValue={opportunity.thesis}
            className={inputClassName}
          />
        </Field>

        <Field label="Next action">
          <textarea
            name="next_action"
            rows={3}
            defaultValue={opportunity.next_action ?? ""}
            className={inputClassName}
          />
        </Field>

        <Field label="Notes">
          <textarea
            name="notes"
            rows={3}
            defaultValue={opportunity.notes ?? ""}
            className={inputClassName}
          />
        </Field>

        <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
          {pending ? "Saving..." : "Save opportunity"}
        </button>
      </form>
    </aside>
  );
}

function StatusPill({ status }: { status: OpportunityStatus }) {
  const tone =
    status === "approved" || status === "active_position"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
      : status === "rejected" || status === "exited"
        ? "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400"
        : "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300";
  return (
    <span className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${tone}`}>
      {statusLabels[status]}
    </span>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      {label}
      {children}
    </label>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
      {children}
    </th>
  );
}

function Td({
  children,
  emphasis = false,
}: {
  children: React.ReactNode;
  emphasis?: boolean;
}) {
  return (
    <td className={`px-5 py-3 ${emphasis ? "font-medium text-zinc-950 dark:text-zinc-50" : "text-zinc-600 dark:text-zinc-300"}`}>
      {children}
    </td>
  );
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function textValue(formData: FormData, key: string) {
  return String(formData.get(key) ?? "").trim();
}
