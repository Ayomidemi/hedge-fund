"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent,
} from "react";
import { inputClassName } from "@/components/ui/form-styles";
import {
  getTickerPrefill,
  getTickerSuggestions,
  type TickerPrefillScope,
  type TickerPrefill,
  type TickerSuggestion,
} from "@/lib/api";
import {
  marketFromTickerSuggestion,
  normalizeTickerInput,
  shouldPrefillTicker,
  type TickerMarket,
} from "@/lib/ticker-prefill-form";

type TickerSelectorProps = {
  autoFocus?: boolean;
  className?: string;
  countryLabel?: string;
  disabled?: boolean;
  detailsScope?: TickerPrefillScope;
  fetchDetailsOnSelect?: boolean;
  id?: string;
  localSuggestions?: TickerSuggestion[];
  allowTypedOption?: boolean;
  market?: TickerMarket;
  marketName?: string | null;
  onDetails?: (prefill: TickerPrefill | null) => void;
  onLoadingChange?: (loading: boolean) => void;
  onMarketChange?: (market: TickerMarket) => void;
  onSuggestion?: (suggestion: TickerSuggestion | null) => void;
  onTickerChange?: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  tickerLabel?: string;
  tickerName?: string | null;
  value?: string;
};

type SelectorOption = TickerSuggestion & {
  typed?: boolean;
};

const SUGGESTION_DEBOUNCE_MS = 220;

export function TickerSelector({
  allowTypedOption = true,
  autoFocus,
  className,
  countryLabel = "Country",
  detailsScope = "identity",
  disabled,
  fetchDetailsOnSelect = true,
  id,
  localSuggestions,
  market,
  marketName = "market",
  onDetails,
  onLoadingChange,
  onMarketChange,
  onSuggestion,
  onTickerChange,
  placeholder = "e.g. AAPL",
  required,
  tickerLabel = "Ticker",
  tickerName = "ticker",
  value,
}: TickerSelectorProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const listboxId = `${inputId}-ticker-options`;
  const [internalMarket, setInternalMarket] = useState<TickerMarket>("US");
  const [internalValue, setInternalValue] = useState("");
  const [suggestions, setSuggestions] = useState<TickerSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const suggestionRequestId = useRef(0);
  const detailsRequestId = useRef(0);
  const activeMarket = market ?? internalMarket;
  const inputValue = value ?? internalValue;
  const normalizedValue = normalizeTickerInput(inputValue);

  const options = useMemo<SelectorOption[]>(() => {
    const exactMatch = suggestions.some(
      (suggestion) => suggestion.ticker === normalizedValue,
    );
    if (
      allowTypedOption &&
      normalizedValue &&
      shouldPrefillTicker(normalizedValue) &&
      !exactMatch
    ) {
      return [
        ...suggestions,
        {
          ticker: normalizedValue,
          name: `Fetch ${normalizedValue}`,
          asset_class: "equity",
          exchange: activeMarket === "NG" ? "NGX" : null,
          currency: activeMarket === "NG" ? "NGN" : "USD",
          sector: null,
          industry: null,
          typed: true,
        },
      ];
    }
    return suggestions;
  }, [activeMarket, allowTypedOption, normalizedValue, suggestions]);

  useEffect(() => {
    const query = normalizeTickerInput(inputValue);
    if (query.length < 1 || disabled) {
      const currentRequest = ++suggestionRequestId.current;
      queueMicrotask(() => {
        if (suggestionRequestId.current !== currentRequest) return;
        setSuggestions([]);
        setSuggestionsLoading(false);
        setActiveIndex(-1);
      });
      return;
    }

    const currentRequest = ++suggestionRequestId.current;
    if (localSuggestions) {
      queueMicrotask(() => {
        if (suggestionRequestId.current !== currentRequest) return;
        const filtered = localSuggestions
          .filter((suggestion) => marketFromTickerSuggestion(suggestion) === activeMarket)
          .filter((suggestion) => suggestionMatchesQuery(suggestion, query))
          .slice(0, 8);
        setSuggestions(filtered);
        setSuggestionsLoading(false);
        setActiveIndex(filtered.length > 0 ? 0 : -1);
      });
      return;
    }

    const timer = window.setTimeout(() => {
      void (async () => {
        setSuggestionsLoading(true);
        try {
          const result = await getTickerSuggestions(query, activeMarket);
          if (suggestionRequestId.current !== currentRequest) return;
          setSuggestions(result);
          setActiveIndex(result.length > 0 ? 0 : -1);
        } catch {
          if (suggestionRequestId.current !== currentRequest) return;
          setSuggestions([]);
          setActiveIndex(-1);
        } finally {
          if (suggestionRequestId.current === currentRequest) {
            setSuggestionsLoading(false);
          }
        }
      })();
    }, SUGGESTION_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [activeMarket, disabled, inputValue, localSuggestions]);

  useEffect(() => {
    onLoadingChange?.(suggestionsLoading || detailsLoading);
  }, [detailsLoading, onLoadingChange, suggestionsLoading]);

  function updateMarket(nextMarket: TickerMarket) {
    suggestionRequestId.current += 1;
    detailsRequestId.current += 1;
    if (market === undefined) {
      setInternalMarket(nextMarket);
    }
    if (value === undefined) {
      setInternalValue("");
    }
    setSuggestions([]);
    setDetailsLoading(false);
    setActiveIndex(-1);
    onDetails?.(null);
    onSuggestion?.(null);
    onTickerChange?.("");
    onMarketChange?.(nextMarket);
  }

  function updateValue(nextValue: string) {
    const nextTicker = nextValue.toUpperCase();
    detailsRequestId.current += 1;
    if (value === undefined) {
      setInternalValue(nextTicker);
    }
    setDetailsLoading(false);
    onDetails?.(null);
    onSuggestion?.(null);
    onTickerChange?.(nextTicker);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    updateValue(event.target.value);
    setOpen(true);
  }

  async function choose(option: SelectorOption) {
    const selectedTicker = option.ticker;
    const selectedMarket = activeMarket;
    const currentDetailsRequest = ++detailsRequestId.current;
    if (value === undefined) {
      setInternalValue(selectedTicker);
    }
    onTickerChange?.(selectedTicker);
    onSuggestion?.(option.typed ? null : option);
    setOpen(false);
    setActiveIndex(-1);

    if (!fetchDetailsOnSelect) return;

    setDetailsLoading(true);
    try {
      const details = await getTickerPrefill(
        selectedTicker,
        selectedMarket,
        detailsScope,
      );
      if (detailsRequestId.current !== currentDetailsRequest) return;
      if (value === undefined) {
        setInternalValue(details.instrument.ticker);
      }
      onTickerChange?.(details.instrument.ticker);
      onDetails?.(details);
    } catch {
      if (detailsRequestId.current !== currentDetailsRequest) return;
      onDetails?.(null);
    } finally {
      if (detailsRequestId.current === currentDetailsRequest) {
        setDetailsLoading(false);
      }
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (!open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
      setOpen(true);
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, options.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === "Enter" && open && activeIndex >= 0) {
      event.preventDefault();
      void choose(options[activeIndex]);
    }
  }

  const showDropdown = open && !disabled && (options.length > 0 || suggestionsLoading);
  const loading = suggestionsLoading || detailsLoading;
  const controlClassName = className ?? inputClassName;

  return (
    <div className="grid gap-3 sm:grid-cols-[140px_minmax(0,1fr)]">
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {countryLabel}
        <select
          className={controlClassName}
          disabled={disabled}
          name={marketName ?? undefined}
          onChange={(event) => updateMarket(event.target.value as TickerMarket)}
          value={activeMarket}
        >
          <option value="US">US</option>
          <option value="NG">Nigeria</option>
        </select>
      </label>
      <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {tickerLabel}
        <div className="relative">
          <input
            aria-activedescendant={
              activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined
            }
            aria-autocomplete="list"
            aria-controls={listboxId}
            aria-expanded={showDropdown}
            autoComplete="off"
            autoFocus={autoFocus}
            className={`${controlClassName} uppercase pr-10`}
            disabled={disabled}
            id={inputId}
            name={tickerName ?? undefined}
            onBlur={() => window.setTimeout(() => setOpen(false), 120)}
            onChange={handleChange}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            required={required}
            role="combobox"
            type="text"
            value={inputValue}
          />
          {loading ? (
            <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-zinc-400">
              ...
            </span>
          ) : null}
          {showDropdown ? (
            <div
              className="absolute z-30 mt-2 max-h-72 w-full overflow-y-auto rounded-lg border border-zinc-200 bg-white py-1 text-sm shadow-xl dark:border-zinc-800 dark:bg-zinc-950"
              id={listboxId}
              role="listbox"
            >
              {options.map((option, index) => (
                <button
                  aria-selected={activeIndex === index}
                  className={`flex w-full items-start justify-between gap-3 px-3 py-2 text-left transition ${
                    activeIndex === index
                      ? "bg-zinc-100 text-zinc-950 dark:bg-zinc-900 dark:text-zinc-50"
                      : "text-zinc-700 hover:bg-zinc-50 dark:text-zinc-300 dark:hover:bg-zinc-900"
                  }`}
                  id={`${listboxId}-${index}`}
                  key={`${option.ticker}-${index}`}
                  onMouseDown={(event) => event.preventDefault()}
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => void choose(option)}
                  role="option"
                  type="button"
                >
                  <span className="min-w-0">
                    <span className="block font-semibold">{option.ticker}</span>
                    <span className="block truncate text-xs text-zinc-500">
                      {option.name}
                    </span>
                  </span>
                  <span className="shrink-0 text-xs text-zinc-400">
                    {option.exchange ?? option.currency}
                  </span>
                </button>
              ))}
              {suggestionsLoading && options.length === 0 ? (
                <div className="px-3 py-2 text-xs text-zinc-500">Searching...</div>
              ) : null}
            </div>
          ) : null}
        </div>
      </label>
    </div>
  );
}

function suggestionMatchesQuery(suggestion: TickerSuggestion, query: string) {
  const haystack = `${suggestion.ticker} ${suggestion.name}`.toUpperCase();
  return haystack.includes(query);
}
