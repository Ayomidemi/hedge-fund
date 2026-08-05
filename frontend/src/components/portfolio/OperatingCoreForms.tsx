"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  createCashLedgerEntry,
  createManualTrade,
  type ManualTradeInput,
} from "@/lib/api";

export function OperatingCoreForms() {
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<"cash" | "trade" | null>(null);
  const router = useRouter();

  async function handleCashSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("Saving cash entry");
    setError(null);
    setPendingAction("cash");

    try {
      const formData = new FormData(form);
      await createCashLedgerEntry({
        amount: String(formData.get("amount") ?? "0"),
        entry_type: String(formData.get("entry_type") ?? "deposit"),
        description: String(formData.get("description") ?? ""),
      });

      setStatus("Cash entry saved");
      form.reset();
      router.refresh();
    } catch {
      setStatus(null);
      setError("Cash entry was not saved.");
    } finally {
      setPendingAction(null);
    }
  }

  async function handleTradeSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setStatus("Saving trade");
    setError(null);
    setPendingAction("trade");

    try {
      const formData = new FormData(form);
      const payload: ManualTradeInput = {
        instrument: {
          ticker: String(formData.get("ticker") ?? ""),
          name: String(formData.get("name") ?? ""),
          asset_class: String(
            formData.get("asset_class") ?? "equity",
          ) as ManualTradeInput["instrument"]["asset_class"],
          exchange: String(formData.get("exchange") ?? ""),
          currency: "USD",
          sector: String(formData.get("sector") ?? ""),
        },
        side: String(formData.get("side") ?? "buy") as ManualTradeInput["side"],
        quantity: String(formData.get("quantity") ?? "0"),
        price: String(formData.get("price") ?? "0"),
        fees: String(formData.get("fees") ?? "0"),
        rationale: String(formData.get("rationale") ?? ""),
        risk_notes: String(formData.get("risk_notes") ?? ""),
      };

      await createManualTrade(payload);

      setStatus("Trade saved");
      form.reset();
      router.refresh();
    } catch {
      setStatus(null);
      setError("Trade was not saved.");
    } finally {
      setPendingAction(null);
    }
  }

  return (
    <section className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
          Journal actions
        </p>
        <h2 className="mt-1 text-base font-semibold">New Entry</h2>
      </div>

      <form
        onSubmit={handleCashSubmit}
        className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Cash</h3>
          <span className="text-xs text-zinc-500">Ledger</span>
        </div>
        <div className="mt-4 grid gap-3">
          <Field label="Amount">
            <input
              name="amount"
              type="number"
              step="0.01"
              required
              className={inputClassName}
            />
          </Field>
          <Field label="Type">
            <select
              name="entry_type"
              className={inputClassName}
            >
              <option value="deposit">Deposit</option>
              <option value="withdrawal">Withdrawal</option>
              <option value="adjustment">Adjustment</option>
            </select>
          </Field>
          <Field label="Description">
            <input
              name="description"
              className={inputClassName}
            />
          </Field>
        </div>
        <button
          className={buttonClassName}
          disabled={pendingAction !== null}
        >
          {pendingAction === "cash" ? "Saving Cash..." : "Save Cash"}
        </button>
      </form>

      <form
        onSubmit={handleTradeSubmit}
        className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold">Trade</h3>
          <span className="text-xs text-zinc-500">Manual</span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <Field label="Ticker">
            <input
              name="ticker"
              required
              className={`${inputClassName} uppercase`}
            />
          </Field>
          <Field label="Name">
            <input
              name="name"
              required
              className={inputClassName}
            />
          </Field>
          <Field label="Asset Class">
            <select
              name="asset_class"
              className={inputClassName}
            >
              <option value="equity">Equity</option>
              <option value="etf">ETF</option>
              <option value="bond">Bond</option>
              <option value="commodity">Commodity</option>
              <option value="cash_equivalent">Cash Equivalent</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Side">
            <select
              name="side"
              className={inputClassName}
            >
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </Field>
          <Field label="Quantity">
            <input
              name="quantity"
              type="number"
              step="0.00000001"
              required
              className={inputClassName}
            />
          </Field>
          <Field label="Price">
            <input
              name="price"
              type="number"
              step="0.000001"
              required
              className={inputClassName}
            />
          </Field>
          <Field label="Fees">
            <input
              name="fees"
              type="number"
              step="0.01"
              defaultValue="0"
              className={inputClassName}
            />
          </Field>
          <Field label="Sector">
            <input
              name="sector"
              className={inputClassName}
            />
          </Field>
          <Field label="Rationale">
            <textarea
              name="rationale"
              required
              rows={3}
              className={inputClassName}
            />
          </Field>
          <Field label="Risk Notes">
            <textarea
              name="risk_notes"
              rows={2}
              className={inputClassName}
            />
          </Field>
        </div>
        <button className={buttonClassName} disabled={pendingAction !== null}>
          {pendingAction === "trade" ? "Saving Trade..." : "Save Trade"}
        </button>
      </form>

      {(status || error) && (
        <p
          className={`rounded-md px-3 py-2 text-xs ${
            error
              ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300"
              : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
          }`}
        >
          {error ?? status}
        </p>
      )}
    </section>
  );
}

const inputClassName =
  "mt-1 w-full rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 outline-none transition focus:border-zinc-950 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-50 dark:focus:border-zinc-200";

const buttonClassName =
  "mt-4 w-full rounded-md bg-zinc-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:bg-zinc-400 dark:bg-zinc-100 dark:text-zinc-950 dark:hover:bg-zinc-300 dark:disabled:bg-zinc-700 dark:disabled:text-zinc-400";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
      {label}
      {children}
    </label>
  );
}
