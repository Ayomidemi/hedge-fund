"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { removeInvestWatchlistItem, type InvestWatchlistItem } from "@/lib/api";
import { money } from "@/components/invest/format";

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
    <ul className="mx-auto max-w-3xl divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      {items.map((item) => (
        <li key={item.id} className="flex items-center justify-between gap-3 p-4">
          <Link href={`/invest/instruments/${item.ticker}`}>
            <p className="font-semibold">{item.ticker}</p>
            <p className="text-sm text-zinc-500">{item.name}</p>
          </Link>
          <div className="flex items-center gap-3">
            <p className="text-sm tabular-nums">{item.price ? money(item.price) : "—"}</p>
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
