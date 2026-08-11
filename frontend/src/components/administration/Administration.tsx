"use client";

import { useMemo, useState } from "react";
import { buttonSecondaryClassName, inputClassName } from "@/components/ui/form-styles";
import { getAdministrationOverview, type AdministrationOverview } from "@/lib/api";

type AdministrationProps = {
  initialOverview: AdministrationOverview | null;
  isUnavailable: boolean;
};

type AdminTab = "logs" | "models" | "data" | "rules" | "policies";

const tabs: { key: AdminTab; label: string }[] = [
  { key: "logs", label: "System logs" },
  { key: "models", label: "Model registry" },
  { key: "data", label: "Data versions" },
  { key: "rules", label: "Portfolio rules" },
  { key: "policies", label: "Risk policies" },
];

const logCategories = [
  "all",
  "portfolio",
  "research",
  "risk",
  "strategy_pods",
  "opportunity",
];

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  month: "short",
  year: "numeric",
});

export function Administration({
  initialOverview,
  isUnavailable,
}: AdministrationProps) {
  const [overview, setOverview] = useState(initialOverview);
  const [activeTab, setActiveTab] = useState<AdminTab>("logs");
  const [logCategory, setLogCategory] = useState("all");
  const [loading, setLoading] = useState(false);

  const logCount = overview?.system_logs.length ?? 0;

  const metrics = useMemo(() => {
    if (!overview) return [];
    return [
      { label: "Log entries", value: String(logCount) },
      { label: "Models", value: String(overview.model_versions.length) },
      { label: "Data sets", value: String(overview.data_versions.length) },
      { label: "Portfolio rules", value: String(overview.portfolio_rules.length) },
      { label: "Risk policies", value: String(overview.risk_policies.length) },
    ];
  }, [logCount, overview]);

  async function refreshLogs(category = logCategory) {
    setLoading(true);
    try {
      const next = await getAdministrationOverview({
        log_limit: 100,
        log_category: category,
      });
      setOverview(next);
    } finally {
      setLoading(false);
    }
  }

  if (!overview) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {isUnavailable
          ? "Administration could not be loaded. Sign in again or refresh."
          : "Administration is not available yet."}
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {overview.portfolio_name}
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Administration</h2>
            <p className="mt-1 text-sm text-zinc-500">
              Registry, rules, and audit trail · {formatDateTime(overview.generated_at)}
            </p>
          </div>
          <button
            type="button"
            onClick={() => refreshLogs()}
            disabled={loading}
            className={buttonSecondaryClassName}
          >
            {loading ? "Refreshing" : "Refresh"}
          </button>
        </div>

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-5 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
          {metrics.map((metric) => (
            <div key={metric.label} className="px-5 py-4">
              <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                {metric.label}
              </p>
              <p className="mt-2 text-xl font-semibold tabular-nums">{metric.value}</p>
            </div>
          ))}
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

      {activeTab === "logs" && (
        <LogsPanel
          logs={overview.system_logs}
          logCategory={logCategory}
          loading={loading}
          onCategoryChange={(category) => {
            setLogCategory(category);
            void refreshLogs(category);
          }}
        />
      )}
      {activeTab === "models" && <ModelsPanel models={overview.model_versions} />}
      {activeTab === "data" && <DataPanel datasets={overview.data_versions} />}
      {activeTab === "rules" && <RulesPanel rules={overview.portfolio_rules} />}
      {activeTab === "policies" && <PoliciesPanel policies={overview.risk_policies} />}
    </div>
  );
}

function LogsPanel({
  logs,
  logCategory,
  loading,
  onCategoryChange,
}: {
  logs: AdministrationOverview["system_logs"];
  logCategory: string;
  loading: boolean;
  onCategoryChange: (category: string) => void;
}) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex flex-wrap items-end justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <div>
          <h3 className="text-sm font-semibold">System logs</h3>
          <p className="mt-1 text-sm text-zinc-500">
            Operational events for your account — trades, research, risk, and pod changes.
          </p>
        </div>
        <select
          value={logCategory}
          onChange={(event) => onCategoryChange(event.target.value)}
          disabled={loading}
          className={`${inputClassName} mt-0 h-10 w-44`}
        >
          {logCategories.map((category) => (
            <option key={category} value={category}>
              {category === "all" ? "All categories" : formatLabel(category)}
            </option>
          ))}
        </select>
      </div>

      <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
        {logs.map((log) => (
          <article key={log.id} className="px-5 py-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                <time dateTime={log.created_at}>{formatDateTime(log.created_at)}</time>
                <span>·</span>
                <span>{formatLabel(log.category)}</span>
                <span>·</span>
                <span className="font-mono">{log.event}</span>
              </div>
              <LevelBadge level={log.level} />
            </div>
            <p className="mt-2 text-sm leading-6 text-zinc-800 dark:text-zinc-200">
              {log.message}
            </p>
            {Object.keys(log.context).length > 0 && (
              <dl className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-zinc-500">
                {Object.entries(log.context).slice(0, 6).map(([key, value]) => (
                  <div key={key}>
                    <span className="font-medium text-zinc-600 dark:text-zinc-400">
                      {formatLabel(key)}:
                    </span>{" "}
                    {String(value)}
                  </div>
                ))}
              </dl>
            )}
          </article>
        ))}
        {logs.length === 0 && (
          <p className="px-5 py-10 text-center text-sm text-zinc-500">
            No log entries yet. Actions like trades, ticker analysis, and risk checks will appear here.
          </p>
        )}
      </div>
    </section>
  );
}

function ModelsPanel({ models }: { models: AdministrationOverview["model_versions"] }) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">Model registry</h3>
        <p className="mt-1 text-sm text-zinc-500">Registered model versions and approved use.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[880px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>Model</Th>
              <Th>Version</Th>
              <Th>Pod</Th>
              <Th>Status</Th>
              <Th>Registered</Th>
            </tr>
          </thead>
          <tbody>
            {models.map((model) => (
              <tr key={model.id} className="border-b border-zinc-100 last:border-0 dark:border-zinc-900">
                <Td emphasis>{model.name}</Td>
                <Td>{model.version}</Td>
                <Td>{formatLabel(model.pod)}</Td>
                <Td>{formatLabel(model.validation_status)}</Td>
                <Td>{formatDateTime(model.created_at)}</Td>
              </tr>
            ))}
            {models.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No models registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function DataPanel({ datasets }: { datasets: AdministrationOverview["data_versions"] }) {
  return (
    <section className="grid gap-4 sm:grid-cols-2">
      {datasets.map((dataset) => (
        <div
          key={dataset.key}
          className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <h3 className="text-sm font-semibold">{dataset.label}</h3>
          <dl className="mt-4 space-y-2 text-sm">
            <Row label="Records" value={dataset.record_count.toLocaleString()} />
            <Row label="Instruments" value={dataset.instrument_count.toLocaleString()} />
            <Row
              label="Latest as of"
              value={dataset.latest_as_of_date ? formatDate(dataset.latest_as_of_date) : "—"}
            />
          </dl>
        </div>
      ))}
    </section>
  );
}

function RulesPanel({ rules }: { rules: AdministrationOverview["portfolio_rules"] }) {
  return (
    <section className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">Portfolio rules</h3>
        <p className="mt-1 text-sm text-zinc-500">Risk limits applied to your operating portfolio.</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              <Th>Name</Th>
              <Th>Type</Th>
              <Th>Threshold</Th>
              <Th>Scope</Th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.name} className="border-b border-zinc-100 last:border-0 dark:border-zinc-900">
                <Td emphasis>{rule.name}</Td>
                <Td>{formatLabel(rule.limit_type)}</Td>
                <Td>
                  {rule.threshold_value} {rule.unit}
                </Td>
                <Td>{formatLabel(rule.scope)}</Td>
              </tr>
            ))}
            {rules.length === 0 && (
              <tr>
                <td colSpan={4} className="px-5 py-10 text-center text-sm text-zinc-500">
                  No portfolio rules configured.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PoliciesPanel({ policies }: { policies: AdministrationOverview["risk_policies"] }) {
  return (
    <section className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="px-5 py-4">
        <h3 className="text-sm font-semibold">Risk policies</h3>
        <p className="mt-1 text-sm text-zinc-500">Versioned risk policy definitions.</p>
      </div>
      {policies.map((policy) => (
        <article key={policy.id} className="px-5 py-4">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h4 className="font-medium">
              {policy.name} · {policy.version}
            </h4>
            <span className="text-xs text-zinc-500">{formatLabel(policy.status)}</span>
          </div>
          <p className="mt-1 text-sm text-zinc-500">
            Effective {formatDateTime(policy.effective_at)} · {policy.limit_count} limits
          </p>
          {policy.notes && (
            <p className="mt-2 text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {policy.notes}
            </p>
          )}
        </article>
      ))}
      {policies.length === 0 && (
        <p className="px-5 py-10 text-center text-sm text-zinc-500">No risk policies on file.</p>
      )}
    </section>
  );
}

function LevelBadge({ level }: { level: string }) {
  const tone =
    level === "error"
      ? "text-red-700 dark:text-red-300"
      : level === "warning"
        ? "text-amber-700 dark:text-amber-300"
        : "text-zinc-500";
  return <span className={`text-xs font-medium uppercase ${tone}`}>{level}</span>;
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="font-medium tabular-nums">{value}</dd>
    </div>
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
    <td
      className={`px-5 py-3 ${
        emphasis ? "font-medium text-zinc-950 dark:text-zinc-50" : "text-zinc-600 dark:text-zinc-300"
      }`}
    >
      {children}
    </td>
  );
}

function formatLabel(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function formatDateTime(value: string) {
  return dateFormatter.format(new Date(value));
}
