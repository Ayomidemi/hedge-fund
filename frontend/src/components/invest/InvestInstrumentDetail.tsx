"use client";

import { FormEvent, useState } from "react";
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
  type InvestInstrument,
} from "@/lib/api";
import { money } from "@/components/invest/format";

export function InvestInstrumentDetail({ instrument }: { instrument: InvestInstrument }) {
  const router = useRouter();
  const [amount, setAmount] = useState("500");
  const [pending, setPending] = useState<"buy" | "watch" | null>(null);
  const price = instrument.price ? Number(instrument.price) : null;
  const estimatedUnits =
    price && Number(amount) > 0 ? (Number(amount) / price).toFixed(4) : "—";

  async function handleBuy(event: FormEvent) {
    event.preventDefault();
    setPending("buy");
    try {
      const order = await createInvestOrder({
        ticker: instrument.ticker,
        side: "BUY",
        amount,
      });
      toast.success(`Order filled for ${instrument.ticker} · ${order.status}`);
      router.push("/invest/portfolio");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Order failed.");
    } finally {
      setPending(null);
    }
  }

  async function handleWatch() {
    setPending("watch");
    try {
      await addInvestWatchlistItem({ ticker: instrument.ticker });
      toast.success(`${instrument.ticker} added to your watchlist.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Watchlist update failed.");
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-sm text-zinc-500">{instrument.name}</p>
        <p className="mt-1 text-3xl font-semibold">
          {instrument.price ? money(instrument.price) : "Price unavailable"}
        </p>
        <p className="mt-2 text-sm text-zinc-500">
          {instrument.sector ?? instrument.asset_class}
          {instrument.exchange ? ` · ${instrument.exchange}` : ""}
        </p>
      </section>

      <form
        onSubmit={(event) => void handleBuy(event)}
        className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-lg font-semibold">Listed-instrument paper order</h2>
        <p className="mt-2 text-sm text-zinc-500">
          This secondary flow is for exchange-listed instruments. Fixed-income
          products use the dedicated bills and bonds detail page.
        </p>
        <label className="mt-4 block text-sm">
          <span className="text-xs uppercase tracking-wide text-zinc-500">Amount</span>
          <input
            value={amount}
            onChange={(event) => setAmount(event.target.value)}
            className={inputClassName}
            inputMode="decimal"
          />
        </label>
        <p className="mt-2 text-sm text-zinc-500">Estimated units: {estimatedUnits}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={pending !== null || !price}
            className={buttonPrimaryClassName}
          >
            {pending === "buy" ? "Submitting..." : "Submit paper order"}
          </button>
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => void handleWatch()}
            className={buttonSecondaryClassName}
          >
            {pending === "watch" ? "Saving…" : "Add to watchlist"}
          </button>
          <Link href="/invest/search" className={buttonSecondaryClassName}>
            Back to search
          </Link>
        </div>
      </form>
    </div>
  );
}
