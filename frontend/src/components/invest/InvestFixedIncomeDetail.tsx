"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import {
  addInvestWatchlistItem,
  createInvestOrder,
  type InvestFixedIncomeProduct,
} from "@/lib/api";
import { money } from "@/components/invest/format";

export function InvestFixedIncomeDetail({
  product,
}: {
  product: InvestFixedIncomeProduct;
}) {
  const router = useRouter();
  const [amount, setAmount] = useState(product.minimum_order_amount);
  const [reviewing, setReviewing] = useState(false);
  const [pending, setPending] = useState<"buy" | "watch" | null>(null);
  const dirtyPrice = Number(product.dirty_price ?? 0);
  const faceIncrement = Number(product.face_value_increment ?? 1);
  const estimatedFaceValue = useMemo(() => {
    const budget = Number(amount);
    if (!Number.isFinite(budget) || budget <= 0 || dirtyPrice <= 0) {
      return null;
    }
    const pricePerFace = dirtyPrice / 100;
    const rawFaceValue = budget / pricePerFace;
    const rounded =
      faceIncrement > 0
        ? Math.floor(rawFaceValue / faceIncrement) * faceIncrement
        : rawFaceValue;
    return rounded > 0 ? rounded : null;
  }, [amount, dirtyPrice, faceIncrement]);
  const canTrade = product.trade_status === "paper_tradable";

  async function handleBuy(event: FormEvent) {
    event.preventDefault();
    if (!canTrade) {
      toast.error("This fixed-income product is not paper-tradable yet.");
      return;
    }
    if (!reviewing) {
      setReviewing(true);
      return;
    }
    setPending("buy");
    try {
      const order = await createInvestOrder({
        ticker: product.ticker,
        side: "BUY",
        amount,
      });
      toast.success(`Paper order filled for ${product.ticker} · ${order.status}`);
      router.push(`/invest/portfolio?placed=${order.id}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Order failed.");
    } finally {
      setPending(null);
    }
  }

  async function handleWatch() {
    setPending("watch");
    try {
      await addInvestWatchlistItem({ ticker: product.ticker });
      toast.success(`${product.ticker} added to your watchlist.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Watchlist update failed.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="w-full space-y-4">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm text-zinc-500">{product.issuer}</p>
            <h2 className="mt-1 text-2xl font-semibold">{product.name}</h2>
            <p className="mt-2 text-sm text-zinc-500">
              {product.instrument_type.replaceAll("_", " ")} · {product.market} ·{" "}
              {product.currency}
            </p>
          </div>
          <span className="rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200">
            {product.trade_status.replaceAll("_", " ")}
          </span>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Yield to maturity" value={percent(product.yield_to_maturity_pct)} />
          <Detail
            label="Dirty price"
            value={`${money(product.dirty_price, product.currency)} / 100`}
          />
          <Detail
            label="Clean price"
            value={`${money(product.clean_price, product.currency)} / 100`}
          />
          <Detail
            label="Accrued interest"
            value={`${money(product.accrued_interest, product.currency)} / 100`}
          />
          <Detail label="Settlement" value={dateLabel(product.settlement_date)} />
          <Detail label="Maturity" value={dateLabel(product.maturity_date)} />
          <Detail
            label="Next coupon"
            value={product.next_coupon_date ? dateLabel(product.next_coupon_date) : "None"}
          />
          <Detail
            label="Face increment"
            value={money(product.face_value_increment, product.currency)}
          />
          <Detail label="Quote time" value={quoteTimeLabel(product.quote_as_of)} />
          <Detail label="Quote status" value={quoteStatusLabel(product)} />
        </div>
      </section>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
          <h3 className="text-lg font-semibold">Projected cashflows</h3>
          <p className="mt-2 text-sm text-zinc-500">
            Amounts are shown per 100 face value using the current quote assumptions.
          </p>
          <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
            {product.cashflows.map((flow) => (
              <li
                key={`${flow.payment_date}-${flow.cashflow_type}`}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <p className="font-medium">{dateLabel(flow.payment_date)}</p>
                  <p className="text-xs capitalize text-zinc-500">
                    {flow.cashflow_type.replaceAll("_", " ")} · {flow.description}
                  </p>
                </div>
                <p className="tabular-nums">
                  {money(flow.amount_per_100, product.currency)}
                </p>
              </li>
            ))}
          </ul>
        </section>

        <form
          onSubmit={(event) => void handleBuy(event)}
          className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <h3 className="text-lg font-semibold">Paper fixed-income order</h3>
          <p className="mt-2 text-sm text-zinc-500">
            Orders use the displayed dirty price and settle into face value units.
            {product.currency !== "USD"
              ? " Paper cash is USD; this amount converts at the stored FX rate."
              : ""}
          </p>
          <label className="mt-4 block text-sm">
            <span className="text-xs uppercase tracking-wide text-zinc-500">
              {product.currency} amount
            </span>
            <input
              value={amount}
              onChange={(event) => {
                setAmount(event.target.value);
                setReviewing(false);
              }}
              className={inputClassName}
              inputMode="decimal"
            />
          </label>
          <div className="mt-3 rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-900">
            <p className="text-zinc-500">Estimated face value</p>
            <p className="mt-1 font-semibold tabular-nums">
              {estimatedFaceValue
                ? money(estimatedFaceValue, product.currency)
                : "Enter an amount"}
            </p>
          </div>
          {reviewing ? (
            <div className="mt-3 rounded-xl bg-zinc-50 p-3 text-sm dark:bg-zinc-900">
              <p className="font-medium">Review paper order</p>
              <p className="mt-1 text-zinc-500">
                Buy about{" "}
                {estimatedFaceValue
                  ? money(estimatedFaceValue, product.currency)
                  : "0"}{" "}
                face value of {product.ticker} for {money(amount, product.currency)}.
              </p>
            </div>
          ) : null}
          {product.quote_stale ? (
            <p className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-950 dark:text-amber-200">
              Quote snapshot is stale. Refresh Markets before relying on this mark.
            </p>
          ) : null}
          <div className="mt-4 flex flex-col gap-2">
            <button
              type="submit"
              disabled={pending !== null || !canTrade}
              className={buttonPrimaryClassName}
            >
              {pending === "buy"
                ? "Submitting..."
                : reviewing
                  ? "Confirm paper order"
                  : "Review order"}
            </button>
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void handleWatch()}
              className={buttonSecondaryClassName}
            >
              {pending === "watch" ? "Saving..." : "Add to watchlist"}
            </button>
            {product.proxy_ticker ? (
              <Link
                href={`/invest/instruments/${product.proxy_ticker}`}
                className={buttonSecondaryClassName}
              >
                {product.proxy_label ?? `Paper with ${product.proxy_ticker}`}
              </Link>
            ) : null}
            <Link href="/invest/markets" className={buttonSecondaryClassName}>
              Back to markets
            </Link>
          </div>
        </form>
      </div>

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h3 className="text-lg font-semibold">Payout and risks</h3>
        <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
          {product.expected_payout}
        </p>
        <ul className="mt-4 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
          {product.retail_notes.map((note, index) => (
            <li key={`${index}-${note}`}>{note}</li>
          ))}
        </ul>
        {product.pricing_assumptions.length ? (
          <div className="mt-5">
            <h4 className="text-sm font-semibold">Pricing assumptions</h4>
            <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
              {product.pricing_assumptions.map((assumption, index) => (
                <li key={`${index}-${assumption}`}>{assumption}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {product.risk_checks.length ? (
          <div className="mt-5 flex flex-wrap gap-2">
            {product.risk_checks.map((check) => (
              <span
                key={check.code}
                className={`rounded-md px-2 py-1 text-xs font-medium ${
                  check.passed
                    ? "bg-zinc-100 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                    : "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200"
                }`}
              >
                {check.code.replaceAll("_", " ")}
              </span>
            ))}
          </div>
        ) : null}
      </section>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold capitalize tabular-nums">{value}</p>
    </div>
  );
}

function percent(value: string | null) {
  if (!value) return "Pending";
  return `${Number(value).toFixed(2)}%`;
}

function dateLabel(value: string | null) {
  if (!value) return "Issue dependent";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(`${value}T00:00:00Z`));
}

function quoteTimeLabel(value: string | null) {
  if (!value) return "Pending";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function quoteStatusLabel(product: InvestFixedIncomeProduct) {
  if (product.quote_stale) return "Stale";
  if (product.quote_is_live) return "Live";
  return product.quote_status?.replaceAll("_", " ") ?? "Indicative";
}
