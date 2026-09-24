"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { money } from "@/components/invest/format";
import { buttonSecondaryClassName, inputClassName } from "@/components/ui/form-styles";
import type { InvestFixedIncomeProduct } from "@/lib/api";

type FilterValue = "ALL" | string;

export function InvestFixedIncomeShelf({
  products,
}: {
  products: InvestFixedIncomeProduct[];
}) {
  const marketOptions = useMemo(
    () => optionValues(products.map((product) => product.market)),
    [products],
  );
  const typeOptions = useMemo(
    () => optionValues(products.map((product) => product.instrument_type)),
    [products],
  );
  const riskOptions = useMemo(
    () => optionValues(products.map((product) => product.risk_level)),
    [products],
  );
  const [market, setMarket] = useState<FilterValue>("ALL");
  const [instrumentType, setInstrumentType] = useState<FilterValue>("ALL");
  const [risk, setRisk] = useState<FilterValue>("ALL");
  const [preview, setPreview] = useState({
    ticker: products[0]?.ticker ?? "",
    amount: products[0]?.minimum_order_amount ?? "",
  });

  const filtered = useMemo(() => {
    return products
      .filter((product) => market === "ALL" || product.market === market)
      .filter(
        (product) =>
          instrumentType === "ALL" || product.instrument_type === instrumentType,
      )
      .filter((product) => risk === "ALL" || product.risk_level === risk)
      .sort((left, right) => {
        const yieldDiff =
          Number(right.yield_to_maturity_pct ?? 0) -
          Number(left.yield_to_maturity_pct ?? 0);
        if (yieldDiff !== 0) return yieldDiff;
        return (left.days_to_maturity ?? 0) - (right.days_to_maturity ?? 0);
      });
  }, [instrumentType, market, products, risk]);

  const selected = useMemo(() => {
    return (
      filtered.find((product) => product.ticker === preview.ticker) ??
      filtered[0] ??
      null
    );
  }, [filtered, preview.ticker]);
  const selectedAmount =
    selected && preview.ticker === selected.ticker
      ? preview.amount
      : selected?.minimum_order_amount ?? "";
  const estimatedFaceValue = selected
    ? estimateFaceValue(selected, selectedAmount)
    : null;
  const highestYield = filtered[0];

  function chooseProduct(product: InvestFixedIncomeProduct) {
    setPreview({
      ticker: product.ticker,
      amount: product.minimum_order_amount,
    });
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 lg:grid-cols-[1fr_1fr_1fr_auto]">
        <FilterSelect
          label="Market"
          value={market}
          options={marketOptions}
          onChange={setMarket}
        />
        <FilterSelect
          label="Instrument"
          value={instrumentType}
          options={typeOptions}
          onChange={setInstrumentType}
        />
        <FilterSelect
          label="Risk"
          value={risk}
          options={riskOptions}
          onChange={setRisk}
        />
        <div className="rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-900">
          <p className="text-xs uppercase tracking-wide text-zinc-500">Shelf</p>
          <p className="mt-1 font-semibold tabular-nums">
            {filtered.length} / {products.length}
          </p>
        </div>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <ShelfStat
          label="Highest YTM"
          value={highestYield ? percent(highestYield.yield_to_maturity_pct) : "-"}
          sublabel={highestYield?.ticker ?? "No match"}
        />
        <ShelfStat
          label="Selected minimum"
          value={
            selected
              ? money(selected.minimum_order_amount, selected.currency)
              : "-"
          }
          sublabel={selected?.ticker ?? "No product selected"}
        />
        <ShelfStat
          label="Quote quality"
          value={selected?.quote_quality_label ?? "Pending"}
          sublabel={selected ? quoteSummary(selected) : "No product selected"}
        />
      </div>

      {filtered.length ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div className="overflow-hidden rounded-xl border border-zinc-200 dark:border-zinc-800">
            {filtered.map((product) => (
              <button
                key={product.ticker}
                type="button"
                onClick={() => chooseProduct(product)}
                className={`w-full border-b border-zinc-100 p-4 text-left transition last:border-b-0 dark:border-zinc-900 ${
                  selected?.ticker === product.ticker
                    ? "bg-zinc-50 shadow-[inset_3px_0_0_rgb(24_24_27)] dark:bg-zinc-900 dark:shadow-[inset_3px_0_0_rgb(244_244_245)]"
                    : "hover:bg-zinc-50 dark:hover:bg-zinc-900"
                }`}
              >
                <div className="grid gap-4 md:grid-cols-[minmax(0,1.35fr)_repeat(4,minmax(84px,auto))] md:items-center">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate font-semibold">{product.name}</p>
                      <span className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
                        {product.market}
                      </span>
                      <QuoteBadge product={product} />
                    </div>
                    <p className="mt-1 truncate text-sm text-zinc-500">
                      {product.issuer} · {product.currency} ·{" "}
                      {product.instrument_type.replaceAll("_", " ")}
                    </p>
                  </div>
                  <Metric label="YTM" value={percent(product.yield_to_maturity_pct)} />
                  <Metric
                    label="Dirty / 100"
                    value={moneyPrecise(product.dirty_price, product.currency)}
                  />
                  <Metric label="Maturity" value={dateLabel(product.maturity_date)} />
                  <Metric
                    label="Minimum"
                    value={money(product.minimum_order_amount, product.currency)}
                  />
                </div>
              </button>
            ))}
          </div>

          {selected ? (
            <aside className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800 lg:sticky lg:top-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-zinc-500">
                    Order preview
                  </p>
                  <h3 className="mt-1 font-semibold">{selected.ticker}</h3>
                </div>
                <span
                  className={`rounded-md px-2 py-1 text-xs font-medium ${quoteBadgeClass(
                    selected,
                  )}`}
                >
                  {selected.quote_quality_label ?? "Pending"}
                </span>
              </div>

              <label className="mt-4 block text-sm">
                <span className="text-xs uppercase tracking-wide text-zinc-500">
                  {selected.currency} amount
                </span>
                <input
                  value={selectedAmount}
                  onChange={(event) =>
                    setPreview({
                      ticker: selected.ticker,
                      amount: event.target.value,
                    })
                  }
                  className={inputClassName}
                  inputMode="decimal"
                />
              </label>

              <div className="mt-3 rounded-lg bg-zinc-50 p-3 text-sm dark:bg-zinc-900">
                <p className="text-zinc-500">Estimated face value</p>
                <p className="mt-1 font-semibold tabular-nums">
                  {estimatedFaceValue
                    ? money(estimatedFaceValue, selected.currency)
                    : "Enter an amount"}
                </p>
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
                <Metric label="Settlement" value={dateLabel(selected.settlement_date)} />
                <Metric
                  label="Next coupon"
                  value={
                    selected.next_coupon_date
                      ? dateLabel(selected.next_coupon_date)
                      : "None"
                  }
                />
                <Metric label="Tenor" value={selected.tenor} />
                <Metric label="Liquidity" value={selected.liquidity} />
              </dl>

              {selected.cashflows.length ? (
                <div className="mt-4">
                  <p className="text-xs uppercase tracking-wide text-zinc-500">
                    Next cashflows
                  </p>
                  <ul className="mt-2 divide-y divide-zinc-100 text-sm dark:divide-zinc-800">
                    {selected.cashflows.slice(0, 3).map((flow) => (
                      <li
                        key={`${selected.ticker}-${flow.payment_date}-${flow.cashflow_type}`}
                        className="flex items-center justify-between gap-3 py-2"
                      >
                        <span>{dateLabel(flow.payment_date)}</span>
                        <span className="tabular-nums">
                          {moneyPrecise(flow.amount_per_100, selected.currency)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {selected.risk_checks.length ? (
                <div className="mt-4 flex flex-wrap gap-2">
                  {selected.risk_checks.map((check) => (
                    <span
                      key={check.code}
                      className={`rounded-md px-2 py-1 text-xs font-medium ${
                        check.passed
                          ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
                          : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200"
                      }`}
                    >
                      {check.code.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
              ) : null}

              <p className="mt-4 text-xs text-zinc-500">
                {quoteSummary(selected)} · {selected.quote_status ?? "indicative"}
              </p>

              <div className="mt-4 flex flex-col gap-2">
                <Link
                  href={`/invest/fixed-income/${selected.ticker}`}
                  className={buttonSecondaryClassName}
                >
                  Open order
                </Link>
                {selected.proxy_ticker ? (
                  <Link
                    href={`/invest/instruments/${selected.proxy_ticker}`}
                    className={buttonSecondaryClassName}
                  >
                    {selected.proxy_label ?? `Open ${selected.proxy_ticker}`}
                  </Link>
                ) : null}
              </div>
            </aside>
          ) : null}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
          No fixed-income products match these filters.
        </div>
      )}
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: FilterValue;
  options: string[];
  onChange: (value: FilterValue) => void;
}) {
  return (
    <label className="block text-sm">
      <span className="text-xs uppercase tracking-wide text-zinc-500">{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={inputClassName}
      >
        <option value="ALL">All</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {labelText(option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ShelfStat({
  label,
  value,
  sublabel,
}: {
  label: string;
  value: string;
  sublabel: string;
}) {
  return (
    <div className="rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-xs text-zinc-500">{sublabel}</p>
    </div>
  );
}

function QuoteBadge({ product }: { product: InvestFixedIncomeProduct }) {
  return (
    <span
      className={`rounded-md px-2 py-1 text-xs font-medium ${quoteBadgeClass(
        product,
      )}`}
    >
      {product.quote_quality_label ?? "Pending"}
    </span>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 truncate font-semibold capitalize tabular-nums">{value}</p>
    </div>
  );
}

function optionValues(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort((a, b) =>
    a.localeCompare(b),
  );
}

function labelText(value: string) {
  return value.replaceAll("_", " ");
}

function percent(value: string | null) {
  if (!value) return "-";
  return `${Number(value).toFixed(2)}%`;
}

function moneyPrecise(value: string | number | null | undefined, currency: string) {
  const amount = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 4,
  }).format(amount);
}

function estimateFaceValue(product: InvestFixedIncomeProduct, amount: string) {
  const budget = Number(amount);
  const dirtyPrice = Number(product.dirty_price ?? 0);
  const faceIncrement = Number(product.face_value_increment ?? 1);
  if (!Number.isFinite(budget) || budget <= 0 || dirtyPrice <= 0) {
    return null;
  }
  const rawFaceValue = budget / (dirtyPrice / 100);
  const rounded =
    faceIncrement > 0
      ? Math.floor(rawFaceValue / faceIncrement) * faceIncrement
      : rawFaceValue;
  return rounded > 0 ? rounded : null;
}

function dateLabel(value: string | null) {
  if (!value) return "Issue dependent";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00Z`));
}

function quoteAge(product: InvestFixedIncomeProduct) {
  if (!product.quote_as_of) return "Quote time pending";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(product.quote_as_of));
}

function quoteSummary(product: InvestFixedIncomeProduct) {
  const provider =
    product.quote_provider_label ?? product.quote_source ?? "Provider pending";
  return `${provider} · ${quoteAge(product)}`;
}

function quoteBadgeClass(product: InvestFixedIncomeProduct) {
  if (product.quote_stale) {
    return "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-200";
  }
  if (product.quote_is_live) {
    return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (product.quote_quality === "seed_model") {
    return "bg-sky-50 text-sky-700 dark:bg-sky-950 dark:text-sky-200";
  }
  return "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200";
}
