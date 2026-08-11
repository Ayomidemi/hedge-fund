import type { TickerPrefill } from "@/lib/api";

/** Minimum ticker length before we hit the prefill API. */
export const TICKER_PREFILL_MIN_LENGTH = 2;

/** Debounce delay — avoids firing on every keystroke. */
export const TICKER_PREFILL_DEBOUNCE_MS = 600;

export type InstrumentFormValues = {
  ticker: string;
  name: string;
  asset_class: string;
  exchange: string;
  currency: string;
  sector: string;
  industry: string;
};

export function normalizeTickerInput(value: string): string {
  return value.trim().toUpperCase();
}

/** Only call prefill when the ticker looks like a real symbol, not noise. */
export function shouldPrefillTicker(ticker: string): boolean {
  const normalized = normalizeTickerInput(ticker);
  if (normalized.length < TICKER_PREFILL_MIN_LENGTH) return false;
  if (normalized.length > 16) return false;
  if (!/[A-Z]/.test(normalized)) return false;
  if (!/^[A-Z0-9.:-]+$/.test(normalized)) return false;
  return true;
}

export function instrumentFieldsFromPrefill(
  prefill: TickerPrefill,
): InstrumentFormValues {
  return {
    ticker: prefill.instrument.ticker,
    name: prefill.instrument.name,
    asset_class: prefill.instrument.asset_class,
    exchange: prefill.instrument.exchange ?? "",
    currency: prefill.instrument.currency,
    sector: prefill.instrument.sector ?? "",
    industry: prefill.instrument.industry ?? "",
  };
}

/** Filter noisy provider warnings — same rules as Ticker Analyst. */
export function isVisiblePrefillWarning(warning: string): boolean {
  const normalized = warning.trim().toLowerCase();
  if (normalized.includes("not available for this api key or plan")) {
    return false;
  }
  if (normalized.includes("was not found by provider")) {
    return false;
  }
  if (normalized.includes("sec companyfacts skipped")) {
    return false;
  }
  if (
    normalized.includes(" returned 404") &&
    ["/v2/", "/v3/", "/stocks/", "/tiingo/", "/companies", "/etfs"].some((prefix) =>
      normalized.startsWith(prefix),
    )
  ) {
    return false;
  }
  return true;
}

export function formatTradeMoney(value: string, currencyCode: string): string {
  try {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currencyCode,
      maximumFractionDigits: currencyCode === "NGN" ? 0 : 2,
    }).format(Number(value));
  } catch {
    return `${currencyCode} ${Number(value).toLocaleString()}`;
  }
}
