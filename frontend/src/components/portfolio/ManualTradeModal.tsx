"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/Modal";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { createManualTrade, type ManualTradeInput } from "@/lib/api";

type ManualTradeModalProps = {
  open: boolean;
  onClose: () => void;
};

export function ManualTradeModal({ open, onClose }: ManualTradeModalProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);

    const formData = new FormData(event.currentTarget);
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

    try {
      await createManualTrade(payload);
      event.currentTarget.reset();
      onClose();
      router.refresh();
    } catch {
      setError("Trade wasn't recorded. Check the fields and try again.");
    } finally {
      setPending(false);
    }
  }

  function handleClose() {
    if (pending) return;
    setError(null);
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Record a trade"
      description="Log a manual execution with rationale. It feeds the position book and trade journal."
      size="lg"
      footer={
        <>
          <button
            type="button"
            className={buttonSecondaryClassName}
            onClick={handleClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="submit"
            form="manual-trade-form"
            className={buttonPrimaryClassName}
            disabled={pending}
          >
            {pending ? "Saving..." : "Save trade"}
          </button>
        </>
      }
    >
      <form id="manual-trade-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ticker">
            <input name="ticker" required className={`${inputClassName} uppercase`} />
          </Field>
          <Field label="Name">
            <input name="name" required className={inputClassName} />
          </Field>
          <Field label="Asset class">
            <select name="asset_class" className={inputClassName}>
              <option value="equity">Equity</option>
              <option value="etf">ETF</option>
              <option value="bond">Bond</option>
              <option value="commodity">Commodity</option>
              <option value="cash_equivalent">Cash equivalent</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Side">
            <select name="side" className={inputClassName}>
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
            <input name="sector" className={inputClassName} />
          </Field>
        </div>

        <Field label="Rationale">
          <textarea name="rationale" required rows={3} className={inputClassName} />
        </Field>

        <Field label="Risk notes">
          <textarea name="risk_notes" rows={2} className={inputClassName} />
        </Field>

        {error && (
          <p className="rounded-xl bg-red-50 px-3.5 py-2.5 text-sm text-red-700 dark:bg-red-950/60 dark:text-red-300">
            {error}
          </p>
        )}
      </form>
    </Modal>
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
