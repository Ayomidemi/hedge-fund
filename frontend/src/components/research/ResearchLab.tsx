"use client";

import { useState } from "react";
import {
  backtests,
  datasets,
  experiments,
  features,
  labStats,
  models,
  notebooks,
  pipelineStages,
  sectionLabels,
  validationChecks,
  type LabSection,
} from "@/components/research/research-lab-data";
import { buttonPrimaryClassName, buttonSecondaryClassName } from "@/components/ui/form-styles";

const sections: LabSection[] = [
  "overview",
  "notebooks",
  "datasets",
  "features",
  "experiments",
  "backtests",
  "models",
];

export function ResearchLab() {
  const [activeSection, setActiveSection] = useState<LabSection>("overview");

  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-6">
      <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-6 py-5 dark:border-zinc-800">
          <div>
            <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Research environment
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">Research Lab</h2>
            <p className="mt-1 max-w-xl text-sm text-zinc-500">
              Hypothesis testing, feature engineering, backtests, and model governance —
              separate from production execution.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={buttonSecondaryClassName}>
              New notebook
            </button>
            <button type="button" className={buttonSecondaryClassName}>
              New experiment
            </button>
            <button type="button" className={buttonPrimaryClassName}>
              Run backtest
            </button>
          </div>
        </div>

        <PipelineBar />

        <div className="grid divide-y divide-zinc-200 sm:grid-cols-4 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
          {labStats.map((stat) => (
            <div key={stat.label} className="px-6 py-4">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                {stat.label}
              </p>
              <p className="mt-1 text-xl font-semibold tabular-nums">{stat.value}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="flex flex-col gap-6 lg:flex-row">
        <nav className="flex shrink-0 gap-1 overflow-x-auto lg:w-48 lg:flex-col lg:overflow-visible">
          {sections.map((section) => (
            <button
              key={section}
              type="button"
              onClick={() => setActiveSection(section)}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-left text-sm transition ${
                activeSection === section
                  ? "bg-zinc-950 font-medium text-white dark:bg-zinc-100 dark:text-zinc-950"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
              }`}
            >
              {sectionLabels[section]}
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {activeSection === "overview" && <OverviewPanel />}
          {activeSection === "notebooks" && <NotebooksPanel />}
          {activeSection === "datasets" && <DatasetsPanel />}
          {activeSection === "features" && <FeaturesPanel />}
          {activeSection === "experiments" && <ExperimentsPanel />}
          {activeSection === "backtests" && <BacktestsPanel />}
          {activeSection === "models" && <ModelsPanel />}
        </div>
      </div>
    </div>
  );
}

function PipelineBar() {
  return (
    <div className="border-b border-zinc-200 px-6 py-4 dark:border-zinc-800">
      <p className="mb-3 text-xs font-medium uppercase tracking-wider text-zinc-500">
        Research pipeline
      </p>
      <div className="flex flex-wrap items-center gap-2">
        {pipelineStages.map((stage, index) => (
          <div key={stage.id} className="flex items-center gap-2">
            <div className="rounded-lg border border-zinc-200 px-3 py-2 dark:border-zinc-700">
              <p className="text-xs text-zinc-500">{stage.label}</p>
              <p className="text-sm font-semibold tabular-nums">{stage.count}</p>
            </div>
            {index < pipelineStages.length - 1 && (
              <span className="text-zinc-300 dark:text-zinc-600">→</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function OverviewPanel() {
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Panel title="Recent experiments" subtitle="Latest hypothesis runs">
        <CompactTable
          headers={["Experiment", "Status", "Sharpe"]}
          rows={experiments.slice(0, 4).map((item) => [
            item.name,
            <StatusBadge key={item.id} label={item.status} />,
            item.sharpe ?? "—",
          ])}
        />
      </Panel>

      <Panel title="Recent backtests" subtitle="Validation runs with costs">
        <CompactTable
          headers={["Backtest", "Sharpe", "Max DD", "Status"]}
          rows={backtests.slice(0, 4).map((item) => [
            item.name,
            item.sharpe,
            item.maxDrawdown,
            <StatusBadge key={item.id} label={item.status} />,
          ])}
        />
      </Panel>

      <Panel title="Data validation" subtitle="Point-in-time integrity checks" className="xl:col-span-2">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            "Missing-value checks",
            "Duplicate detection",
            "Timestamp validation",
            "Corporate-action adjustment",
            "Survivorship-bias prevention",
            "Point-in-time handling",
            "Data-version tracking",
            "Look-ahead-bias prevention",
          ].map((check) => (
            <div
              key={check}
              className="flex items-center justify-between rounded-lg border border-zinc-200 px-3 py-2.5 dark:border-zinc-800"
            >
              <span className="text-sm text-zinc-700 dark:text-zinc-300">{check}</span>
              <span className="text-xs font-medium text-zinc-500">Active</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function NotebooksPanel() {
  return (
    <Panel title="Notebooks" subtitle="Exploratory research — not connected to live execution">
      <DataTable
        headers={["Notebook", "Owner", "Last edited", "Linked experiment", "Status"]}
        rows={notebooks.map((item) => [
          <span key={item.id} className="font-medium">{item.name}</span>,
          item.owner,
          item.lastEdited,
          item.linkedExperiment ?? "—",
          <StatusBadge key={`${item.id}-status`} label={item.status} />,
        ])}
      />
    </Panel>
  );
}

function DatasetsPanel() {
  return (
    <Panel title="Datasets" subtitle="Versioned research data with validation status">
      <DataTable
        headers={["Dataset", "Source", "Records", "Frequency", "Version", "Updated", "Validation"]}
        rows={datasets.map((item) => [
          <span key={item.id} className="font-medium">{item.name}</span>,
          item.source,
          item.records,
          item.frequency,
          item.version,
          item.updated,
          <StatusBadge key={`${item.id}-val`} label={item.validation} />,
        ])}
      />
    </Panel>
  );
}

function FeaturesPanel() {
  return (
    <Panel title="Feature registry" subtitle="Reusable signals and factors for models">
      <DataTable
        headers={["Feature", "Version", "Category", "Used by", "Updated"]}
        rows={features.map((item) => [
          <span key={item.id} className="font-medium">{item.name}</span>,
          item.version,
          item.category,
          `${item.usedBy} models`,
          item.updated,
        ])}
      />
    </Panel>
  );
}

function ExperimentsPanel() {
  return (
    <Panel title="Experiments" subtitle="Tracked hypothesis → model development">
      <DataTable
        headers={["Experiment", "Hypothesis", "Model", "Owner", "Status", "Sharpe", "Created"]}
        rows={experiments.map((item) => [
          <span key={item.id} className="font-medium">{item.name}</span>,
          <span key={`${item.id}-hyp`} className="max-w-xs truncate text-zinc-500">{item.hypothesis}</span>,
          item.modelType,
          item.owner,
          <StatusBadge key={`${item.id}-status`} label={item.status} />,
          item.sharpe ?? "—",
          item.created,
        ])}
      />
    </Panel>
  );
}

function BacktestsPanel() {
  return (
    <Panel title="Backtests" subtitle="Walk-forward, cost-adjusted, benchmark-compared">
      <DataTable
        headers={[
          "Backtest",
          "Strategy",
          "Period",
          "Sharpe",
          "Max DD",
          "Alpha",
          "Walk-fwd",
          "Costs",
          "Status",
        ]}
        rows={backtests.map((item) => [
          <span key={item.id} className="font-medium">{item.name}</span>,
          item.strategy,
          item.period,
          item.sharpe,
          item.maxDrawdown,
          item.benchmarkAlpha,
          item.walkForward ? "Yes" : "No",
          item.costsIncluded ? "Yes" : "No",
          <StatusBadge key={`${item.id}-status`} label={item.status} />,
        ])}
      />
    </Panel>
  );
}

function ModelsPanel() {
  return (
    <div className="space-y-6">
      <Panel title="Model comparison" subtitle="Registry entries with validation progress">
        <DataTable
          headers={[
            "Model",
            "Version",
            "Stage",
            "Sharpe",
            "OOS Sharpe",
            "Validation",
            "Confidence",
          ]}
          rows={models.map((item) => [
            <div key={item.id}>
              <p className="font-medium">{item.name}</p>
              <p className="mt-0.5 text-xs text-zinc-500">{item.purpose}</p>
            </div>,
            item.version,
            <StatusBadge key={`${item.id}-stage`} label={item.stage} />,
            item.sharpe,
            item.oosSharpe,
            `${item.validationsPassed}/${item.validationsTotal}`,
            <StatusBadge key={`${item.id}-conf`} label={item.confidence} />,
          ])}
        />
      </Panel>

      <Panel title="Validation requirements" subtitle="From model governance — all must pass before promotion">
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {validationChecks.map((check, index) => (
            <div
              key={check}
              className="flex items-center gap-3 rounded-lg border border-zinc-200 px-3 py-2.5 dark:border-zinc-800"
            >
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-zinc-300 text-[10px] font-medium text-zinc-500 dark:border-zinc-600">
                {index + 1}
              </span>
              <span className="text-sm text-zinc-700 dark:text-zinc-300">{check}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Panel({
  title,
  subtitle,
  children,
  className = "",
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 ${className}`}
    >
      <div className="border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <h3 className="text-sm font-semibold">{title}</h3>
        <p className="mt-0.5 text-sm text-zinc-500">{subtitle}</p>
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function DataTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-zinc-200 dark:border-zinc-800">
            {headers.map((header) => (
              <th
                key={header}
                className="pb-3 pr-4 text-xs font-medium uppercase tracking-wider text-zinc-500 last:pr-0"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="border-b border-zinc-100 last:border-0 dark:border-zinc-900"
            >
              {row.map((cell, cellIndex) => (
                <td
                  key={cellIndex}
                  className="py-3 pr-4 text-zinc-800 last:pr-0 dark:text-zinc-200"
                >
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

function CompactTable({
  headers,
  rows,
}: {
  headers: string[];
  rows: React.ReactNode[][];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            {headers.map((header) => (
              <th
                key={header}
                className="pb-2 pr-3 text-xs font-medium uppercase tracking-wider text-zinc-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-zinc-100 dark:border-zinc-900">
              {row.map((cell, cellIndex) => (
                <td key={cellIndex} className="py-2.5 pr-3 text-zinc-800 dark:text-zinc-200">
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

function StatusBadge({ label }: { label: string }) {
  const formatted = label
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

  return (
    <span className="inline-flex rounded-md border border-zinc-200 bg-white px-2 py-0.5 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
      {formatted}
    </span>
  );
}
