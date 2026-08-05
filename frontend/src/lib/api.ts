export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function fetchApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    next: { revalidate: 0 },
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function postApi<TResponse, TPayload>(
  path: string,
  payload: TPayload,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<TResponse>;
}

export type HealthResponse = {
  status: string;
};

export function getHealth() {
  return fetchApi<HealthResponse>("/api/health");
}

export function getApiInfo() {
  return fetchApi<{ message: string }>("/");
}

export type Instrument = {
  id: string;
  ticker: string;
  name: string;
  asset_class: string;
  exchange: string | null;
  currency: string;
  sector: string | null;
  industry: string | null;
};

export type Portfolio = {
  id: string;
  name: string;
  base_currency: string;
  mandate: string | null;
  initial_capital: string;
};

export type CashLedgerEntry = {
  id: string;
  portfolio_id: string;
  entry_date: string;
  amount: string;
  currency: string;
  entry_type: string;
  description: string | null;
  source_reference: string | null;
};

export type Position = {
  id: string;
  instrument: Instrument;
  quantity: string;
  average_cost: string;
  market_value: string;
  unrealized_pnl: string;
};

export type Trade = {
  id: string;
  instrument: Instrument;
  trade_date: string;
  side: "buy" | "sell";
  status: string;
  quantity: string;
  executed_price: string | null;
  fees: string;
  rationale: string;
  risk_notes: string | null;
  broker_reference: string | null;
};

export type RiskLimit = {
  id: string;
  name: string;
  limit_type: string;
  threshold_value: string;
  unit: string;
  scope: string;
  severity: string;
  is_active: boolean;
  notes: string | null;
};

export type RiskCheck = {
  name: string;
  limit_type: string;
  observed_value: string;
  threshold_value: string;
  unit: string;
  passed: boolean;
  severity: string;
  message: string;
};

export type ExposureBucket = {
  name: string;
  exposure_pct: string;
};

export type OperatingCoreDashboard = {
  portfolio: Portfolio;
  cash_balance: string;
  nav: string;
  invested_value: string;
  open_position_count: number;
  trade_count: number;
  positions: Position[];
  recent_cash_entries: CashLedgerEntry[];
  recent_trades: Trade[];
  risk_limits: RiskLimit[];
  risk_checks: RiskCheck[];
  asset_class_exposure: ExposureBucket[];
  sector_exposure: ExposureBucket[];
};

export type CashLedgerEntryInput = {
  amount: string;
  entry_type: string;
  description?: string;
};

export type ManualTradeInput = {
  instrument: {
    ticker: string;
    name: string;
    asset_class: "equity" | "etf" | "bond" | "commodity" | "cash_equivalent" | "other";
    exchange?: string;
    currency: string;
    sector?: string;
    industry?: string;
  };
  side: "buy" | "sell";
  quantity: string;
  price: string;
  fees: string;
  rationale: string;
  risk_notes?: string;
};

export function getOperatingCoreDashboard() {
  return fetchApi<OperatingCoreDashboard>("/api/operating-core/dashboard");
}

export function getCashLedgerHistory() {
  return fetchApi<CashLedgerEntry[]>("/api/operating-core/cash-ledger/history");
}

export function createCashLedgerEntry(payload: CashLedgerEntryInput) {
  return postApi<CashLedgerEntry, CashLedgerEntryInput>(
    "/api/operating-core/cash-ledger",
    payload,
  );
}

export function createManualTrade(payload: ManualTradeInput) {
  return postApi<Trade, ManualTradeInput>("/api/operating-core/trades", payload);
}
