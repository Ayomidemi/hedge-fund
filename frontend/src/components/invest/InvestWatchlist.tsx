"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { removeInvestWatchlistItem, type InvestWatchlistItem } from "@/lib/api";
import { money, signedPercent } from "@/components/invest/format";

export function InvestWatchlist({ items }: { items: InvestWatchlistItem[] }) {
  const router = useRouter();

  async function handleRemove(ticker: string) {
    try {
      await removeInvestWatchlistItem(ticker);
      toast.success(`${ticker} removed.`);
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not remove.");
    }
  }

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        Nothing saved yet.{" "}
        <Link href="/invest/search" className="font-medium underline">
          Search
        </Link>{" "}
        and add a name.
      </div>
    );
  }

  return (
    <ul className="mx-auto max-w-4xl divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <Link href={item.href} className="min-w-0">
            <p className="font-semibold">{item.ticker}</p>
            <p className="truncate text-sm text-zinc-500">{item.name}</p>
            <p className="mt-1 text-xs capitalize text-zinc-500">
              {(item.asset_class ?? "instrument").replaceAll("_", " ")}
            </p>
          </Link>
          <div className="flex flex-wrap items-center gap-3 sm:justify-end">
            <div className="text-sm tabular-nums">
              <p className="font-medium">
                {item.price ? money(item.price, item.currency) : "-"}
              </p>
              <p className={changeClass(item.change_pct)}>
                {signedPercent(item.change_pct)}
              </p>
            </div>
            <Link href={item.href} className={buttonSecondaryClassName}>
              Open
            </Link>
            <button
              type="button"
              className={buttonSecondaryClassName}
              onClick={() => void handleRemove(item.ticker)}
            >
              Remove
            </button>
          </div>
        </li>
      ))}
    </ul>
  );
}

function changeClass(value: string | null | undefined) {
  const amount = Number(value ?? 0);
  if (amount > 0) return "text-xs text-emerald-700 dark:text-emerald-300";
  if (amount < 0) return "text-xs text-red-700 dark:text-red-300";
  return "text-xs text-zinc-500";
}
