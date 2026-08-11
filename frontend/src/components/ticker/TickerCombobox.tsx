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
  getTickerSuggestions,
  type TickerSuggestion,
} from "@/lib/api";
import {
  normalizeTickerInput,
  shouldPrefillTicker,
} from "@/lib/ticker-prefill-form";

type TickerComboboxProps = {
  autoFocus?: boolean;
  className?: string;
  defaultValue?: string;
  disabled?: boolean;
  id?: string;
  name?: string;
  onChange?: (value: string) => void;
  onSelect?: (suggestion: TickerSuggestion | null) => void;
  placeholder?: string;
  required?: boolean;
  value?: string;
};

const SUGGESTION_DEBOUNCE_MS = 220;

export function TickerCombobox({
  autoFocus,
  className,
  defaultValue = "",
  disabled,
  id,
  name,
  onChange,
  onSelect,
  placeholder = "e.g. AAPL",
  required,
  value,
}: TickerComboboxProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const listboxId = `${inputId}-ticker-options`;
  const [internalValue, setInternalValue] = useState(defaultValue);
  const [suggestions, setSuggestions] = useState<TickerSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const requestId = useRef(0);
  const inputValue = value ?? internalValue;
  const normalizedValue = normalizeTickerInput(inputValue);

  const options = useMemo(() => {
    const exactMatch = suggestions.some(
      (suggestion) => suggestion.ticker === normalizedValue,
    );
    if (normalizedValue && shouldPrefillTicker(normalizedValue) && !exactMatch) {
      return [
        ...suggestions,
        {
          ticker: normalizedValue,
          name: `Use ${normalizedValue}`,
          asset_class: "equity" as const,
          exchange: null,
          currency: "USD",
          sector: null,
          industry: null,
        },
      ];
    }
    return suggestions;
  }, [normalizedValue, suggestions]);

  useEffect(() => {
    const query = normalizeTickerInput(inputValue);
    if (query.length < 1 || disabled) {
      const currentRequest = ++requestId.current;
      queueMicrotask(() => {
        if (requestId.current !== currentRequest) return;
        setSuggestions([]);
        setLoading(false);
        setActiveIndex(-1);
      });
      return;
    }

    const currentRequest = ++requestId.current;
    const timer = window.setTimeout(() => {
      void (async () => {
        setLoading(true);
        try {
          const result = await getTickerSuggestions(query);
          if (requestId.current !== currentRequest) return;
          setSuggestions(result);
          setActiveIndex(result.length > 0 ? 0 : -1);
        } catch {
          if (requestId.current !== currentRequest) return;
          setSuggestions([]);
          setActiveIndex(-1);
        } finally {
          if (requestId.current === currentRequest) {
            setLoading(false);
          }
        }
      })();
    }, SUGGESTION_DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
  }, [disabled, inputValue]);

  function updateValue(nextValue: string) {
    const nextTicker = nextValue.toUpperCase();
    if (value === undefined) {
      setInternalValue(nextTicker);
    }
    onChange?.(nextTicker);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    updateValue(event.target.value);
    setOpen(true);
  }

  function choose(option: TickerSuggestion) {
    updateValue(option.ticker);
    setOpen(false);
    setActiveIndex(-1);
    onSelect?.(suggestions.find((item) => item.ticker === option.ticker) ?? null);
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
      choose(options[activeIndex]);
    }
  }

  const showDropdown = open && !disabled && (options.length > 0 || loading);

  return (
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
        className={`${className ?? inputClassName} uppercase pr-10`}
        disabled={disabled}
        id={inputId}
        name={name}
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
              onClick={() => choose(option)}
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
          {loading && options.length === 0 ? (
            <div className="px-3 py-2 text-xs text-zinc-500">Searching...</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
