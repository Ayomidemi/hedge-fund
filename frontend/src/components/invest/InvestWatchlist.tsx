"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { removeInvestWatchlistItem, type InvestWatchlistItem } from "@/lib/api";
import { money, signedPercent } from "@/components/invest/format";

export function InvestWatchlist({
  items,
  error = null,
}: {
  items: InvestWatchlistItem[];
  error?: string | null;
}) {
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

  if (error) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="w-full rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        Nothing saved yet.{" "}
        <Link href="/invest/markets" className="font-medium underline">
          Search
        </Link>{" "}
        and add a name.
      </div>
    );
  }

  return (
    <ul className="w-full divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
      {items.map((item) => (
        <li
          key={item.id}
          className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div className="min-w-0">
            <Link href={item.href}>
              <p className="font-semibold">{item.ticker}</p>
              <p className="truncate text-sm text-zinc-500">{item.name}</p>
              <p className="mt-1 text-xs capitalize text-zinc-500">
                {(item.asset_class ?? "instrument").replaceAll("_", " ")}
              </p>
              {item.notes ? (
                <p className="mt-1 line-clamp-2 text-xs text-zinc-500">{item.notes}</p>
              ) : null}
            </Link>
            {item.headline ? (
              <Link
                href={`/invest/news?ticker=${encodeURIComponent(item.ticker)}`}
                className="mt-2 line-clamp-2 block text-xs text-zinc-500 hover:underline"
              >
                {item.headline}
              </Link>
            ) : null}
            {item.unusual && item.unusual_label ? (
              <p className="mt-1 text-xs text-amber-800 dark:text-amber-200">
                {item.unusual_label}
              </p>
            ) : null}
          </div>
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
