import type { ReactNode } from "react";

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function LabPanel({
  children,
  subtitle,
  title,
}: {
  children: ReactNode;
  subtitle?: string;
  title: string;
}) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mb-4">
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="mt-1 text-sm text-zinc-500">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${statusStyle(status)}`}
    >
      {formatLabel(status)}
    </span>
  );
}

export function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

export function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

export function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function pct(value: string | number) {
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${numeric.toFixed(1)}%`;
}

export function parseTickerList(value: string) {
  return uniqueTickers(
    value
      .split(/[\s,]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean),
  );
}

export function uniqueTickers(tickers: string[]) {
  return Array.from(new Set(tickers));
}

export function todayDateValue() {
  return new Date().toISOString().slice(0, 10);
}

export function dateYearsAgoValue(years: number) {
  const date = new Date();
  date.setFullYear(date.getFullYear() - years);
  return date.toISOString().slice(0, 10);
}

function statusStyle(status: string) {
  if (["completed", "passed", "validated", "ready", "candidate"].includes(status)) {
    return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300";
  }
  if (["warning", "needs_review", "blocked", "design"].includes(status)) {
    return "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300";
  }
  if (["failed", "archived"].includes(status)) {
    return "bg-rose-50 text-rose-700 dark:bg-rose-950 dark:text-rose-300";
  }
  return "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300";
}
