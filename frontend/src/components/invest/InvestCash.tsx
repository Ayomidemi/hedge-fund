"use client";

import { FormEvent, useRef, useState } from "react";
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
import { newIdempotencyKey } from "@/lib/idempotency";

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
  const depositKey = useRef<string | null>(null);

  async function handleDeposit(event: FormEvent) {
    event.preventDefault();
    if (!depositKey.current) {
      depositKey.current = newIdempotencyKey();
    }
    setPending("add");
    try {
      await addInvestPaperCash(amount, { idempotencyKey: depositKey.current });
      depositKey.current = null;
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
      <div className="rounded-sm border border-red-200 bg-red-50 p-5 text-sm text-red-800">
        Cash account could not be loaded.
      </div>
    );
  }

  const deposits = transactions
    .filter((item) => item.currency === account.base_currency && item.amount && Number(item.amount) > 0)
    .reduce((sum, item) => sum + Number(item.amount), 0);
  const outflows = transactions
    .filter((item) => item.currency === account.base_currency && item.amount && Number(item.amount) < 0)
    .reduce((sum, item) => sum + Math.abs(Number(item.amount)), 0);

  return (
    <div className="w-full space-y-8">
      <div><p className="mb-2 text-xs text-stone-500">Paper account · {account.account_number}</p><h2 className="text-3xl sm:text-4xl">Your cash.</h2></div>
      <div className="grid gap-8 border-y border-[var(--pease-rule)] bg-[var(--pease-paper)] px-5 py-7 sm:px-7 lg:grid-cols-[1.2fr_1fr]">
        <section>
          <p className="text-sm text-stone-500">Total cash · {account.base_currency}</p>
          <p className="mt-2 text-[clamp(2rem,5vw,3.5rem)] leading-tight tabular-nums">{money(account.cash, account.base_currency)}</p>
          <p className="mt-3 text-sm text-stone-500">Buying power <span className="ml-2 font-medium text-[var(--pease-ink)]">{money(account.buying_power, account.base_currency)}</span></p>
          <dl className="mt-7 grid grid-cols-2 gap-5 border-t border-[var(--pease-rule)] pt-4 text-sm">
            <div><dt className="text-stone-500">Recent inflows</dt><dd className="mt-1 tabular-nums">{money(deposits, account.base_currency)}</dd></div>
            <div><dt className="text-stone-500">Recent outflows</dt><dd className="mt-1 tabular-nums">{money(outflows, account.base_currency)}</dd></div>
          </dl>
          <p className="mt-3 text-xs text-stone-500">Recorded cash movements include trading activity.</p>
        </section>
        <form onSubmit={(event) => void handleDeposit(event)} className="border-t border-[var(--pease-rule)] pt-6 lg:border-l lg:border-t-0 lg:pl-8 lg:pt-0">
          <h2 className="text-xl">Add paper cash</h2>
          <p className="mt-2 text-sm text-stone-500">Add simulated funds to this Invest account.</p>
          <label htmlFor="invest-deposit-amount" className="mt-5 block text-sm">Amount ({account.base_currency})</label>
          <input id="invest-deposit-amount" type="number" min="0.01" step="any" required value={amount} onChange={(event) => setAmount(event.target.value)} className={inputClassName} inputMode="decimal" />
          <button type="submit" disabled={pending !== null} className={`${buttonPrimaryClassName} mt-4`}>{pending === "add" ? "Adding…" : "Add paper cash"}</button>
        </form>
      </div>
      <section className="rounded-sm border border-stone-300/70 bg-[#fffefb] p-6 dark:border-zinc-800 dark:bg-[#151613]">
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
                  {signedMoney(item.amount, item.currency)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <details className="border-t border-[var(--pease-rule)] pt-4 text-sm">
        <summary className="w-fit cursor-pointer text-stone-500">Paper account settings</summary>
        <p className="mt-3 text-sm text-stone-500">Reset the simulated account to its opening state.</p>
        <button type="button" disabled={pending !== null} onClick={() => void handleReset()} className={`${buttonSecondaryClassName} mt-3`}>{pending === "reset" ? "Resetting…" : "Reset paper account"}</button>
      </details>
    </div>
  );
}
