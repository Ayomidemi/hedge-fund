"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/Modal";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createManualTrade,
  updateManualTrade,
  type ManualTradeInput,
  type TradeJournalEntry,
} from "@/lib/api";

type ManualTradeModalProps = {
  initialTrade?: TradeJournalEntry | null;
  open: boolean;
  onClose: () => void;
};

export function ManualTradeModal({
  initialTrade = null,
  open,
  onClose,
}: ManualTradeModalProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const isEditing = Boolean(initialTrade);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setPending(true);

    const formData = new FormData(form);
    const tradeDate = String(formData.get("trade_date") ?? "");
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
        industry: String(formData.get("industry") ?? ""),
      },
      side: String(formData.get("side") ?? "buy") as ManualTradeInput["side"],
      quantity: String(formData.get("quantity") ?? "0"),
      price: String(formData.get("price") ?? "0"),
      fees: String(formData.get("fees") ?? "0"),
      trade_date: tradeDate ? new Date(tradeDate).toISOString() : undefined,
      rationale: String(formData.get("rationale") ?? ""),
      risk_notes: String(formData.get("risk_notes") ?? ""),
      broker_reference: String(formData.get("broker_reference") ?? ""),
    };

    try {
      if (initialTrade) {
        await updateManualTrade(initialTrade.id, payload);
        toast.success(`${payload.instrument.ticker.toUpperCase()} trade updated.`);
      } else {
        await createManualTrade(payload);
        toast.success(`${payload.instrument.ticker.toUpperCase()} trade recorded.`);
        form.reset();
      }
      onClose();
      router.refresh();
    } catch (caught) {
      toast.error(
        caught instanceof Error
          ? caught.message
          : "Trade wasn't saved. Check the fields and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  function handleClose() {
    if (pending) return;
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={isEditing ? "Edit trade" : "Record a trade"}
      description={
        isEditing
          ? "Update the execution record. The cash movement and position book will be rebuilt from the trade ledger."
          : "Log a manual execution with rationale. It feeds the position book and trade journal."
      }
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
            {pending ? "Saving..." : isEditing ? "Save changes" : "Save trade"}
          </button>
        </>
      }
    >
      <form
        key={initialTrade?.id ?? "new"}
        id="manual-trade-form"
        onSubmit={handleSubmit}
        className="space-y-4"
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Ticker">
            <input
              name="ticker"
              required
              defaultValue={initialTrade?.instrument.ticker ?? ""}
              className={`${inputClassName} uppercase`}
            />
          </Field>
          <Field label="Name">
            <input
              name="name"
              required
              defaultValue={initialTrade?.instrument.name ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Asset class">
            <select
              name="asset_class"
              defaultValue={initialTrade?.instrument.asset_class ?? "equity"}
              className={inputClassName}
            >
              <option value="equity">Equity</option>
              <option value="etf">ETF</option>
              <option value="bond">Bond</option>
              <option value="commodity">Commodity</option>
              <option value="cash_equivalent">Cash equivalent</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Side">
            <select
              name="side"
              defaultValue={initialTrade?.side ?? "buy"}
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
              defaultValue={initialTrade?.quantity ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Price">
            <input
              name="price"
              type="number"
              step="0.000001"
              required
              defaultValue={initialTrade?.executed_price ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Fees">
            <input
              name="fees"
              type="number"
              step="0.01"
              defaultValue={initialTrade?.fees ?? "0"}
              className={inputClassName}
            />
          </Field>
          <Field label="Sector">
            <input
              name="sector"
              defaultValue={initialTrade?.instrument.sector ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Exchange">
            <input
              name="exchange"
              defaultValue={initialTrade?.instrument.exchange ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Industry">
            <input
              name="industry"
              defaultValue={initialTrade?.instrument.industry ?? ""}
              className={inputClassName}
            />
          </Field>
          <Field label="Trade date">
            <input
              name="trade_date"
              type="datetime-local"
              required
              defaultValue={toDateTimeLocalValue(initialTrade?.trade_date)}
              className={inputClassName}
            />
          </Field>
          <Field label="Broker reference">
            <input
              name="broker_reference"
              defaultValue={initialTrade?.broker_reference ?? ""}
              className={inputClassName}
            />
          </Field>
        </div>

        <Field label="Rationale">
          <textarea
            name="rationale"
            required
            rows={3}
            defaultValue={initialTrade?.rationale ?? ""}
            className={inputClassName}
          />
        </Field>

        <Field label="Risk notes">
          <textarea
            name="risk_notes"
            rows={2}
            defaultValue={initialTrade?.risk_notes ?? ""}
            className={inputClassName}
          />
        </Field>
      </form>
    </Modal>
  );
}

function toDateTimeLocalValue(value?: string) {
  const date = value ? new Date(value) : new Date();
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
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
