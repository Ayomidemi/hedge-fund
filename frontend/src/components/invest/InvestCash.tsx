"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import {
  addInvestPaperCash,
  resetInvestPaperAccount,
  type InvestAccount,
  type InvestTransaction,
} from "@/lib/api";
import { money, signedMoney } from "@/components/invest/format";

export function InvestCash({
  account,
  transactions,
}: {
  account: InvestAccount | null;
  transactions: InvestTransaction[];
}) {
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

  const deposits = transactions
    .filter((item) => item.amount && Number(item.amount) > 0)
    .reduce((sum, item) => sum + Number(item.amount), 0);
  const outflows = transactions
    .filter((item) => item.amount && Number(item.amount) < 0)
    .reduce((sum, item) => sum + Math.abs(Number(item.amount)), 0);

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">Cash</p>
        <p className="mt-2 text-3xl font-semibold tabular-nums">{money(account.cash)}</p>
        <p className="mt-2 text-sm text-zinc-500">
          Buying power {money(account.buying_power)} · paper only
        </p>
        <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-900">
            <p className="text-xs uppercase tracking-wide text-zinc-500">Ledger inflow</p>
            <p className="mt-1 font-semibold tabular-nums">{money(deposits)}</p>
          </div>
          <div className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-900">
            <p className="text-xs uppercase tracking-wide text-zinc-500">Ledger outflow</p>
            <p className="mt-1 font-semibold tabular-nums">{money(outflows)}</p>
          </div>
        </div>
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

      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <h2 className="text-lg font-semibold">Recent ledger</h2>
        {transactions.length === 0 ? (
          <p className="mt-3 text-sm text-zinc-500">No ledger entries yet.</p>
        ) : (
          <ul className="mt-4 divide-y divide-zinc-100 dark:divide-zinc-900">
            {transactions.slice(0, 8).map((item) => (
              <li
                key={item.id}
                className="flex items-center justify-between gap-3 py-3 text-sm"
              >
                <div>
                  <p className="font-medium">
                    {item.entry_type.replaceAll("_", " ")}
                    {item.ticker ? ` · ${item.ticker}` : ""}
                  </p>
                  <p className="text-xs text-zinc-500">
                    {new Date(item.occurred_at).toLocaleString()}
                    {item.description ? ` · ${item.description}` : ""}
                  </p>
                </div>
                <p className="tabular-nums">
                  {signedMoney(item.amount)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
