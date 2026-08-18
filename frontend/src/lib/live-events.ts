export type LiveQuote = {
  ticker: string;
  price: string;
  change_pct: string | null;
  currency: string;
  source: string;
  as_of: string;
};

export type QuoteBatchUpdatedPayload = {
  quotes: LiveQuote[];
  as_of: string;
};

export type PortfolioMarkedPayload = {
  portfolio_id: string;
  nav: string;
  cash_balance: string;
  invested_value: string;
  position_count: number;
};

export type PriceRefreshCompletedPayload = {
  run_id: string;
  ticker_count: number;
  success_count: number;
  failure_count: number;
  positions_marked: number;
  status: string;
};

export type FxRateUpdatedPayload = {
  base_currency: string;
  quote_currency: string;
  rate: string;
  source: string;
  as_of: string;
  pair_label: string;
};

export type SystemLogEntryPayload = {
  level: string;
  category: string;
  event: string;
  message: string;
};

export type NewsPollCompletedPayload = {
  run_id: string;
  status: string;
  trigger: string;
  target_scope: string | null;
  target_key: string | null;
  provider_calls: number;
  items_seen: number;
  items_created: number;
  items_updated: number;
  cache_hit: boolean;
};

export type PlatformEvent =
  | { type: "quote.batch_updated"; emitted_at: string; owner_user_id: string | null; payload: QuoteBatchUpdatedPayload }
  | { type: "portfolio.marked"; emitted_at: string; owner_user_id: string | null; payload: PortfolioMarkedPayload }
  | { type: "price_refresh.completed"; emitted_at: string; owner_user_id: string | null; payload: PriceRefreshCompletedPayload }
  | { type: "fx.rate_updated"; emitted_at: string; owner_user_id: string | null; payload: FxRateUpdatedPayload }
  | { type: "system_log.entry"; emitted_at: string; owner_user_id: string | null; payload: SystemLogEntryPayload }
  | { type: "news.poll_completed"; emitted_at: string; owner_user_id: string | null; payload: NewsPollCompletedPayload };

export function parsePlatformEvent(data: string): PlatformEvent | null {
  try {
    const parsed = JSON.parse(data) as PlatformEvent;
    if (!parsed || typeof parsed.type !== "string") {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
