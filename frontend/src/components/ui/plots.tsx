type HorizontalBarDatum = {
  detail?: string;
  label: string;
  tone?: "neutral" | "positive" | "negative" | "warning";
  value: number;
  valueLabel?: string;
};

type HorizontalBarPlotProps = {
  data: HorizontalBarDatum[];
  empty?: string;
  maxItems?: number;
};

export function HorizontalBarPlot({
  data,
  empty = "No data to plot",
  maxItems = 8,
}: HorizontalBarPlotProps) {
  const visibleData = data.slice(0, maxItems);
  const values = visibleData.map((item) => item.value);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const span = maxValue - minValue || 1;
  const zeroPct = ((0 - minValue) / span) * 100;

  if (visibleData.length === 0) {
    return <p className="text-sm text-zinc-500">{empty}</p>;
  }

  return (
    <div className="space-y-3">
      {visibleData.map((item) => {
        const startPct =
          item.value >= 0 ? zeroPct : ((item.value - minValue) / span) * 100;
        const widthPct = Math.max((Math.abs(item.value) / span) * 100, 1.5);
        return (
          <div key={`${item.label}-${item.value}`}>
            <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
              <div className="min-w-0">
                <p className="truncate font-medium text-zinc-700 dark:text-zinc-300">
                  {item.label}
                </p>
                {item.detail ? (
                  <p className="truncate text-zinc-500">{item.detail}</p>
                ) : null}
              </div>
              <span className="shrink-0 tabular-nums text-zinc-500">
                {item.valueLabel ?? item.value.toLocaleString()}
              </span>
            </div>
            <div className="relative h-2.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-900">
              {minValue < 0 && maxValue > 0 ? (
                <div
                  className="absolute top-0 h-full w-px bg-zinc-300 dark:bg-zinc-700"
                  style={{ left: `${zeroPct}%` }}
                />
              ) : null}
              <div
                className={`absolute top-0 h-full rounded-full ${barToneClass(item.tone, item.value)}`}
                style={{
                  left: `${startPct}%`,
                  width: `${Math.min(widthPct, 100)}%`,
                }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function barToneClass(
  tone: HorizontalBarDatum["tone"],
  value: number,
) {
  if (tone === "positive") return "bg-emerald-500";
  if (tone === "negative") return "bg-rose-500";
  if (tone === "warning") return "bg-amber-500";
  if (value > 0) return "bg-emerald-500";
  if (value < 0) return "bg-rose-500";
  return "bg-zinc-900 dark:bg-zinc-100";
}
