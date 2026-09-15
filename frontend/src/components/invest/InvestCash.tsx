"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { addInvestPaperCash, resetInvestPaperAccount, type InvestAccount } from "@/lib/api";
import { money } from "@/components/invest/format";

export function InvestCash({ account }: { account: InvestAccount | null }) {
  const router = useRouter();
  const [amount, setAmount] = useState("1000");
  const [pending, setPending] = useState<"add" | "reset" | null>(null);

  async function handleDeposit(event: FormEvent) {
    event.preventDefault();
    setPending("add");
    try {
      await addInvestPaperCash(amount);
      toast.success("Paper cash added.");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Deposit failed.");
    } finally {
      setPending(null);
    }
  }

  async function handleReset() {
    setPending("reset");
    try {
      await resetInvestPaperAccount();
      toast.success("Paper account reset.");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reset failed.");
    } finally {
      setPending(null);
    }
  }

  if (!account) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        Cash account could not be loaded.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Cash</p>
        <p className="mt-2 text-3xl font-semibold tabular-nums">{money(account.cash)}</p>
        <p className="mt-2 text-sm text-zinc-500">
          Buying power {money(account.buying_power)} · paper only
        </p>
      </section>
      <form
        onSubmit={(event) => void handleDeposit(event)}
        className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-lg font-semibold">Add paper cash</h2>
        <input
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          className={inputClassName}
          inputMode="decimal"
        />
        <div className="mt-4 flex flex-wrap gap-2">
          <button type="submit" disabled={pending !== null} className={buttonPrimaryClassName}>
            {pending === "add" ? "Adding…" : "Add paper cash"}
          </button>
          <button
            type="button"
            disabled={pending !== null}
            onClick={() => void handleReset()}
            className={buttonSecondaryClassName}
          >
            {pending === "reset" ? "Resetting…" : "Reset paper account"}
          </button>
        </div>
      </form>
    </div>
  );
}
