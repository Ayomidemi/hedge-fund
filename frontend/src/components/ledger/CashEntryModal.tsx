"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  cashEntryDescriptions,
  cashPlatformSuggestions,
} from "@/components/ledger/cash-ledger-ui";
import { Modal } from "@/components/ui/Modal";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createCashAdjustment,
  createCashDeposit,
  createCashWithdrawal,
} from "@/lib/api";

const entryTypes = [
  { value: "deposit" as const, label: "Deposit", hint: "Capital in" },
  { value: "withdrawal" as const, label: "Withdrawal", hint: "Capital out" },
  { value: "adjustment" as const, label: "Adjustment", hint: "Correction" },
];

type EntryType = (typeof entryTypes)[number]["value"];

type CashEntryModalProps = {
  open: boolean;
  onClose: () => void;
};

export function CashEntryModal({ open, onClose }: CashEntryModalProps) {
  const router = useRouter();
  const [entryType, setEntryType] = useState<EntryType>("deposit");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setPending(true);
    setError(null);

    const formData = new FormData(form);
    const payload = {
      amount: String(formData.get("amount") ?? "0"),
      platform: String(formData.get("platform") ?? "Manual"),
      description: String(formData.get("description") ?? ""),
    };

    try {
      if (entryType === "deposit") {
        await createCashDeposit(payload);
      } else if (entryType === "withdrawal") {
        await createCashWithdrawal(payload);
      } else {
        await createCashAdjustment({
          ...payload,
          description: payload.description.trim(),
        });
      }

      form.reset();
      setEntryType("deposit");
      onClose();
      router.refresh();
    } catch (submitError) {
      const message =
        submitError instanceof Error && submitError.message
          ? submitError.message
          : "That entry didn't save. Check the fields and try again.";
      setError(message);
    } finally {
      setPending(false);
    }
  }

  function handleClose() {
    if (pending) return;
    setError(null);
    onClose();
  }

  const noteRequired = entryType === "adjustment";
  const selectedType = entryTypes.find((type) => type.value === entryType);

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title="Record cash movement"
      description={cashEntryDescriptions[entryType]}
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
            form="cash-entry-form"
            className={buttonPrimaryClassName}
            disabled={pending}
          >
            {pending ? "Saving..." : `Save ${selectedType?.label.toLowerCase() ?? "entry"}`}
          </button>
        </>
      }
    >
      <form id="cash-entry-form" onSubmit={handleSubmit} className="space-y-5">
        <fieldset className="space-y-3">
          <legend className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            Movement type
          </legend>
          <div className="grid gap-2 sm:grid-cols-3">
            {entryTypes.map((type) => {
              const selected = entryType === type.value;
              return (
                <button
                  key={type.value}
                  type="button"
                  onClick={() => setEntryType(type.value)}
                  className={`rounded-lg border px-3 py-3 text-left transition ${
                    selected
                      ? "border-zinc-950 bg-zinc-950 text-white dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-950"
                      : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-400 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:border-zinc-500"
                  }`}
                >
                  <span className="block text-sm font-medium">{type.label}</span>
                  <span
                    className={`mt-0.5 block text-xs ${
                      selected ? "text-zinc-300 dark:text-zinc-500" : "text-zinc-500"
                    }`}
                  >
                    {type.hint}
                  </span>
                </button>
              );
            })}
          </div>
        </fieldset>

        <label className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Platform
          <input
            name="platform"
            list="cash-platform-suggestions"
            defaultValue="Manual"
            required
            placeholder="e.g. Bamboo, Alpaca, Interactive Brokers..."
            className={inputClassName}
          />
          <datalist id="cash-platform-suggestions">
            {cashPlatformSuggestions.map((platform) => (
              <option key={platform} value={platform} />
            ))}
          </datalist>
        </label>

        <label className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Amount
          <div className="relative mt-1.5">
            <span className="pointer-events-none absolute inset-y-0 left-3.5 flex items-center text-sm text-zinc-400">
              $
            </span>
            <input
              name="amount"
              type="number"
              step="0.01"
              min={entryType === "adjustment" ? undefined : "0.01"}
              required
              placeholder="0.00"
              className={`${inputClassName} pl-8`}
            />
          </div>
          {entryType === "withdrawal" && (
            <p className="mt-1.5 text-xs text-zinc-500">
              Enter a positive amount — it will be recorded as an outflow.
            </p>
          )}
          {entryType === "adjustment" && (
            <p className="mt-1.5 text-xs text-zinc-500">
              Use a negative amount to reduce cash, positive to increase it.
            </p>
          )}
        </label>

        <label className="block text-sm font-medium text-zinc-900 dark:text-zinc-100">
          Note
          {!noteRequired && <span className="ml-1 font-normal text-zinc-400">optional</span>}
          <input
            name="description"
            required={noteRequired}
            placeholder={
              entryType === "adjustment"
                ? "Explain what you're correcting and why..."
                : "e.g. Initial fund capital, broker transfer..."
            }
            className={inputClassName}
          />
        </label>

        {error && (
          <p className="rounded-lg border border-red-200 bg-white px-3.5 py-2.5 text-sm text-red-700 dark:border-red-900 dark:bg-zinc-950 dark:text-red-400">
            {error}
          </p>
        )}
      </form>
    </Modal>
  );
}
