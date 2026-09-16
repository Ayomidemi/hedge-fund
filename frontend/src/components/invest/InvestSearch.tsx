"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import {
  buttonPrimaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { searchInvestInstruments, type InvestInstrument } from "@/lib/api";
import { money } from "@/components/invest/format";

export function InvestSearch() {
  const [query, setQuery] = useState("T-BILL");
  const [results, setResults] = useState<InvestInstrument[]>([]);
  const [pending, setPending] = useState(false);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    try {
      setResults(await searchInvestInstruments(query));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <form onSubmit={(event) => void handleSearch(event)} className="flex gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={`${inputClassName} mt-0`}
          placeholder="Search bills, bonds, funds, or listed names"
        />
        <button type="submit" disabled={pending} className={buttonPrimaryClassName}>
          {pending ? "Searching…" : "Search"}
        </button>
      </form>
      <ul className="mt-5 divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950">
        {results.length === 0 ? (
          <li className="p-5 text-sm text-zinc-500">
            Search the shared instrument registry. Try T-BILL, Treasury, FGN, or a fund.
          </li>
        ) : (
          results.map((item) => (
            <li key={item.ticker}>
              <Link
                href={hrefForInstrument(item)}
                className="flex items-center justify-between p-4 hover:bg-zinc-50 dark:hover:bg-zinc-900"
              >
                <div>
                  <p className="font-semibold">{item.ticker}</p>
                  <p className="text-sm text-zinc-500">{item.name}</p>
                </div>
                <p className="text-sm tabular-nums">
                  {item.price ? money(item.price) : "—"}
                </p>
              </Link>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function hrefForInstrument(item: InvestInstrument) {
  if (
    item.sector === "Fixed Income" ||
    item.asset_class === "bond" ||
    item.asset_class === "cash_equivalent"
  ) {
    return `/invest/fixed-income/${item.ticker}`;
  }
  return `/invest/instruments/${item.ticker}`;
}
