"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import {
  buttonPrimaryClassName,
  inputControlClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import {
  searchInvestInstruments,
  type InvestInstrument,
  type InvestSearchMarket,
} from "@/lib/api";
import { money } from "@/components/invest/format";

type InvestSearchProps = {
  initialQuery?: string;
  initialMarket?: string;
  markets?: InvestSearchMarket[];
  variant?: "page" | "embedded";
};

export function InvestSearch({
  initialMarket,
  initialQuery = "",
  markets = [],
  variant: _variant = "page",
}: InvestSearchProps) {
  const marketOptions = markets.filter((option) => option.code && option.label);
  const defaultMarket = initialMarket || marketOptions[0]?.code || "";
  const [query, setQuery] = useState(initialQuery);
  const [market, setMarket] = useState(defaultMarket);
  const [results, setResults] = useState<InvestInstrument[]>([]);
  const [pending, setPending] = useState(false);
  const [lastSearch, setLastSearch] = useState<{
    query: string;
    market: string;
  } | null>(null);

  async function handleSearch(event: FormEvent) {
    event.preventDefault();
    const normalizedQuery = query.trim();
    if (!normalizedQuery) {
      setResults([]);
      setLastSearch(null);
      return;
    }
    if (!market) {
      toast.error("No search market is configured.");
      return;
    }

    setPending(true);
    try {
      setResults(await searchInvestInstruments(normalizedQuery, market));
      setLastSearch({ query: normalizedQuery, market });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Search failed.");
    } finally {
      setPending(false);
    }
  }

  function updateMarket(nextMarket: string) {
    setMarket(nextMarket);
    setResults([]);
    setLastSearch(null);
  }

  const isEmbedded = _variant === "embedded";

  return (
    <div className="w-full">
      <form
        onSubmit={(event) => void handleSearch(event)}
        className="grid gap-2 sm:grid-cols-[1fr_auto_auto]"
      >
        <label className="sr-only" htmlFor="invest-instrument-search">
          Search instruments
        </label>
        <input
          id="invest-instrument-search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          className={inputControlClassName}
          placeholder="Search bills, bonds, funds, or listed names"
        />
        <div
          aria-label="Market"
          className="inline-flex rounded-xl border border-zinc-200 bg-zinc-50 p-1 dark:border-zinc-800 dark:bg-zinc-900"
        >
          {marketOptions.map((option) => (
            <button
              key={option.code}
              type="button"
              onClick={() => updateMarket(option.code)}
              aria-pressed={market === option.code}
              className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                market === option.code
                  ? "bg-white text-zinc-950 shadow-sm dark:bg-zinc-950 dark:text-zinc-50"
                  : "text-zinc-500 hover:text-zinc-950 dark:text-zinc-400 dark:hover:text-zinc-50"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
        <button
          type="submit"
          disabled={pending || !market}
          className={buttonPrimaryClassName}
        >
          {pending ? "Searching..." : "Search"}
        </button>
      </form>

      <ul
        className={
          isEmbedded
            ? "mt-4 divide-y divide-zinc-100 border-t border-zinc-100 dark:divide-zinc-900 dark:border-zinc-900"
            : "mt-5 divide-y divide-zinc-100 rounded-2xl border border-zinc-200 bg-white dark:divide-zinc-900 dark:border-zinc-800 dark:bg-zinc-950"
        }
      >
        {results.length === 0 ? (
          <li className={isEmbedded ? "py-4 text-sm text-zinc-500" : "p-5 text-sm text-zinc-500"}>
            {lastSearch
              ? `No ${marketLabel(lastSearch.market, marketOptions)} matches for "${lastSearch.query}".`
              : "Search fixed income, funds, or listed names."}
          </li>
        ) : (
          results.map((item) => (
            <li key={item.ticker}>
              <Link
                href={hrefForInstrument(item)}
                className={`flex items-center justify-between gap-4 hover:bg-zinc-50 dark:hover:bg-zinc-900 ${
                  isEmbedded ? "py-3" : "p-4"
                }`}
              >
                <div>
                  <p className="font-semibold">
                    {item.ticker}{" "}
                    <span className="font-normal text-zinc-500">
                      {item.exchange ?? item.asset_class}
                    </span>
                  </p>
                  <p className="text-sm text-zinc-500">{item.name}</p>
                </div>
                <p className="shrink-0 text-sm tabular-nums">
                  {item.price ? money(item.price, item.currency) : "—"}
                </p>
              </Link>
            </li>
          ))
        )}
      </ul>
    </div>
  );
}

function marketLabel(market: string, markets: InvestSearchMarket[]) {
  return markets.find((option) => option.code === market)?.label ?? market;
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
