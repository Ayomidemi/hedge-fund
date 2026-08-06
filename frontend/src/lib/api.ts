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
    let detail = `Request failed (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: string | { msg?: string }[] };
      if (typeof body.detail === "string") {
        detail = body.detail;
      } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
        detail = body.detail[0].msg;
      }
    } catch {
      // keep default message
    }
    throw new Error(detail);
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
  platform: string;
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

export type CashMovementInput = {
  amount: string;
  platform: string;
  description?: string;
};

export type CashLedgerEntryInput = CashMovementInput & {
  entry_type: string;
};

export function createCashDeposit(payload: CashMovementInput) {
  return postApi<CashLedgerEntry, CashMovementInput>(
    "/api/operating-core/cash-ledger/deposits",
    payload,
  );
}

export function createCashWithdrawal(payload: CashMovementInput) {
  return postApi<CashLedgerEntry, CashMovementInput>(
    "/api/operating-core/cash-ledger/withdrawals",
    payload,
  );
}

export function createCashAdjustment(payload: CashMovementInput & { description: string }) {
  return postApi<CashLedgerEntry, CashMovementInput & { description: string }>(
    "/api/operating-core/cash-ledger/adjustments",
    payload,
  );
}

export function createCashLedgerEntry(payload: CashLedgerEntryInput) {
  return createCashDeposit(payload);
}

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

export type TickerMetricsInput = {
  current_price?: string | null;
  market_cap_billion?: string | null;
  pe_ratio?: string | null;
  forward_pe?: string | null;
  revenue_growth_pct?: string | null;
  earnings_growth_pct?: string | null;
  free_cash_flow_yield_pct?: string | null;
  net_margin_pct?: string | null;
  debt_to_equity?: string | null;
  price_vs_200d_pct?: string | null;
  relative_strength_6m_pct?: string | null;
  volatility_30d_pct?: string | null;
};

export type TickerAnalysisInput = {
  instrument: {
    ticker: string;
    name: string;
    asset_class: "equity" | "etf" | "bond" | "commodity" | "cash_equivalent" | "other";
    exchange?: string;
    currency: string;
    sector?: string;
    industry?: string;
  };
  metrics: TickerMetricsInput;
  time_horizon: string;
  investment_question?: string;
  thesis: string;
  bull_case?: string;
  base_case?: string;
  bear_case?: string;
  thesis_breakers?: string;
  risk_notes?: string;
  source_reference?: string;
};

export type TickerAIDraftInput = {
  instrument: TickerAnalysisInput["instrument"];
  metrics: TickerMetricsInput;
  time_horizon: string;
  source_reference?: string;
  source_warnings: string[];
  user_notes?: string;
};

export type TickerAIDraft = {
  prompt_version: string;
  model: string;
  investment_question: string;
  analyst_questions: string[];
  thesis: string;
  bull_case: string;
  base_case: string;
  bear_case: string;
  thesis_breakers: string;
  risk_notes: string;
  missing_data_warnings: string[];
  confidence_notes: string;
};

export type TickerScore = {
  name: string;
  score: string;
  weight: string;
  notes: string;
};

export type TickerMemo = {
  id: string;
  instrument: Instrument;
  recommendation_id: string | null;
  memo_date: string;
  classification: string;
  time_horizon: string | null;
  executive_view: string;
  thesis: string;
  bull_case: string | null;
  base_case: string | null;
  bear_case: string | null;
  thesis_breakers: string | null;
  risk_assessment: string | null;
  scores: Record<string, unknown>;
  data_timestamp: string;
  model_version_label: string | null;
};

export type TickerAnalysis = {
  memo: TickerMemo;
  action: string;
  confidence_score: string;
  conviction_score: string;
  recommended_weight: string;
  composite_score: string;
  classification: string;
  scorecard: TickerScore[];
  evidence_summary: string;
};

export type TickerMemoSummary = {
  id: string;
  ticker: string;
  name: string;
  asset_class: string;
  memo_date: string;
  classification: string;
  executive_view: string;
  composite_score: string | null;
  action: string | null;
  confidence_score: string | null;
};

export type TickerPrefill = {
  instrument: {
    ticker: string;
    name: string;
    asset_class: TickerAnalysisInput["instrument"]["asset_class"];
    exchange: string | null;
    currency: string;
    sector: string | null;
    industry: string | null;
  };
  metrics: TickerMetricsInput;
  provider: string;
  source_reference: string;
  data_timestamp: string;
  source_warnings: string[];
  raw_sources: Record<string, unknown>;
};

export function getOperatingCoreDashboard() {
  return fetchApi<OperatingCoreDashboard>("/api/operating-core/dashboard");
}

export function getCashLedgerHistory() {
  return fetchApi<CashLedgerEntry[]>("/api/operating-core/cash-ledger/history");
}

export function createManualTrade(payload: ManualTradeInput) {
  return postApi<Trade, ManualTradeInput>("/api/operating-core/trades", payload);
}

export function getRecentTickerMemos() {
  return fetchApi<TickerMemoSummary[]>("/api/ticker-intelligence/memos");
}

export function getTickerMemo(memoId: string) {
  return fetchApi<TickerMemo>(
    `/api/ticker-intelligence/memos/${encodeURIComponent(memoId)}`,
  );
}

export function getTickerPrefill(ticker: string) {
  return fetchApi<TickerPrefill>(
    `/api/ticker-intelligence/${encodeURIComponent(ticker)}/prefill`,
  );
}

export function createTickerAIDraft(payload: TickerAIDraftInput) {
  return postApi<TickerAIDraft, TickerAIDraftInput>(
    "/api/ticker-intelligence/ai/draft",
    payload,
  );
}

export function createTickerAnalysis(payload: TickerAnalysisInput) {
  return postApi<TickerAnalysis, TickerAnalysisInput>(
    "/api/ticker-intelligence/analyze",
    payload,
  );
}
