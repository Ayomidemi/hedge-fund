"use client";

import { useMemo, useState } from "react";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import {
  normalizeTickerInput,
  shouldPrefillTicker,
  type TickerMarket,
} from "@/lib/ticker-prefill-form";

type TickerListSelectorProps = {
  defaultTickers?: string[];
  disabled?: boolean;
  maxTickers?: number;
  name: string;
  placeholder?: string;
};

export function TickerListSelector({
  defaultTickers = [],
  disabled,
  maxTickers = 500,
  name,
  placeholder = "Add ticker",
}: TickerListSelectorProps) {
  const [market, setMarket] = useState<TickerMarket>("US");
  const [candidate, setCandidate] = useState("");
  const [tickers, setTickers] = useState(() => unique(defaultTickers));
  const normalizedCandidate = normalizeTickerInput(candidate);
  const canAdd =
    !disabled &&
    shouldPrefillTicker(normalizedCandidate) &&
    !tickers.includes(normalizedCandidate) &&
    tickers.length < maxTickers;

  const submittedValue = useMemo(() => tickers.join(", "), [tickers]);

  function addCandidate() {
    if (!canAdd) return;
    setTickers((current) => unique([...current, normalizedCandidate]));
    setCandidate("");
  }

  function removeTicker(ticker: string) {
    setTickers((current) => current.filter((item) => item !== ticker));
  }

  return (
    <div className="space-y-3">
      <input type="hidden" name={name} value={submittedValue} />
      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <TickerSelector
          allowTypedOption
          disabled={disabled}
          fetchDetailsOnSelect={false}
          market={market}
          marketName={null}
          onMarketChange={setMarket}
          onTickerChange={setCandidate}
          placeholder={placeholder}
          tickerName={null}
          value={candidate}
        />
        <button
          type="button"
          className={`${buttonSecondaryClassName} h-10`}
          disabled={!canAdd}
          onClick={addCandidate}
        >
          Add
        </button>
      </div>
      <div className="min-h-10 rounded-lg border border-zinc-200 bg-white p-2 dark:border-zinc-800 dark:bg-zinc-950">
        {tickers.length === 0 ? (
          <p className="px-1 py-1 text-sm text-zinc-500">No tickers selected.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {tickers.map((ticker) => (
              <span
                key={ticker}
                className="inline-flex items-center gap-1.5 rounded-md border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs font-medium text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
              >
                {ticker}
                <button
                  type="button"
                  aria-label={`Remove ${ticker}`}
                  className="rounded px-1 text-zinc-500 hover:bg-zinc-200 hover:text-zinc-950 dark:hover:bg-zinc-800 dark:hover:text-zinc-50"
                  disabled={disabled}
                  onClick={() => removeTicker(ticker)}
                >
                  x
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function unique(values: string[]) {
  return Array.from(
    new Set(
      values
        .map((value) => normalizeTickerInput(value))
        .filter((value) => shouldPrefillTicker(value)),
    ),
  );
}
