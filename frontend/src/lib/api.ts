export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiRequestOptions = {
  accessToken?: string;
};

async function resolveAccessToken(
  explicit?: string,
): Promise<string | undefined> {
  if (explicit) {
    return explicit;
  }

  if (typeof window === "undefined") {
    return undefined;
  }

  const { createClient, isSupabaseConfigured } = await import("@/lib/supabase/client");
  if (!isSupabaseConfigured()) {
    return undefined;
  }

  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  return data.session?.access_token;
}

function buildAuthHeaders(accessToken?: string): HeadersInit {
  const headers: Record<string, string> = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  return headers;
}

async function fetchApi<T>(
  path: string,
  options?: ApiRequestOptions,
): Promise<T> {
  const accessToken = await resolveAccessToken(options?.accessToken);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    next: { revalidate: 0 },
    headers: buildAuthHeaders(accessToken),
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

async function postApi<TResponse, TPayload>(
  path: string,
  payload: TPayload,
  options?: ApiRequestOptions,
): Promise<TResponse> {
  const accessToken = await resolveAccessToken(options?.accessToken);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(accessToken),
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

export function getHealth(options?: ApiRequestOptions) {
  return fetchApi<HealthResponse>("/api/health", options);
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

export type ComparativeMetric = {
  metric: string;
  value: string;
  history_percentile: string | null;
  sector_percentile: string | null;
  universe_percentile: string | null;
  peer_count: number;
};

export type TickerComparative = {
  ticker: string;
  as_of_date: string;
  feature_version: string;
  sector: string | null;
  metrics: ComparativeMetric[];
};

export type TickerPrediction = {
  ticker: string;
  model_version_id: string;
  model_version: string;
  as_of_date: string;
  horizon_days: number;
  expected_relative_return_pct: string;
  downside_p05_relative_return_pct: string;
  probability_outperform: string;
  confidence_score: string;
  feature_version: string;
  drivers: {
    feature: string;
    value_zscore: number;
    contribution_pct: number;
  }[];
};

export type PortfolioFit = {
  ticker: string;
  portfolio_fit_score: string;
  improves_portfolio: boolean;
  current_position_weight: string;
  proposed_weight: string;
  pro_forma_weight: string;
  concentration_after: string;
  sector_exposure_after: string;
  notes: string[];
};

export type ModelComparisonRow = {
  model_version_id: string;
  model_name: string;
  model_version: string;
  horizon_days: number | null;
  feature_version: string | null;
  training_rows: number | null;
  validation_rows: number | null;
  validation_mae: string | null;
  validation_r2: string | null;
  validation_directional_accuracy: string | null;
  residual_p05_pct: string | null;
  created_at: string;
};

export type TickerMLReport = {
  ticker: string;
  comparative: TickerComparative | null;
  prediction: TickerPrediction | null;
  portfolio_fit: PortfolioFit | null;
  model_comparison: ModelComparisonRow[];
  warnings: string[];
};

export type RegimeState = {
  state_id: number;
  label: string;
  probability: string;
  mean_return_pct: string;
  volatility_pct: string;
  observation_count: number;
};

export type RegimeModel = {
  model_version_id: string;
  model_name: string;
  model_version: string;
  ticker: string;
  as_of_date: string;
  current_regime: string;
  confidence_score: string;
  state_probabilities: RegimeState[];
  transition_matrix: string[][];
  warnings: string[];
};

export type BacktestPeriod = {
  as_of_date: string;
  selected_tickers: string[];
  strategy_return_pct: string;
  benchmark_return_pct: string | null;
  alpha_pct: string | null;
  turnover_pct: string;
  cost_drag_pct: string;
};

export type BacktestRunInput = {
  tickers: string[];
  benchmark_ticker?: string | null;
  horizon_days?: number;
  feature_version?: string;
  label_source?: string;
  top_n?: number;
  min_names_per_period?: number;
  transaction_cost_bps?: string;
};

export type BacktestRun = {
  backtest_id: string;
  name: string;
  start_date: string | null;
  end_date: string | null;
  horizon_days: number;
  rebalance_count: number;
  selected_count_avg: string;
  cumulative_return_pct: string;
  benchmark_return_pct: string | null;
  alpha_pct: string | null;
  annualized_return_pct: string;
  annualized_volatility_pct: string;
  sharpe_ratio: string;
  max_drawdown_pct: string;
  hit_rate_pct: string;
  turnover_pct: string;
  cost_drag_pct: string;
  periods: BacktestPeriod[];
  warnings: string[];
};

export type MonthlyReport = {
  month: string;
  generated_at: string;
  portfolio_name: string;
  nav: string;
  cash_balance: string;
  invested_value: string;
  monthly_cash_flow: string;
  monthly_trade_count: number;
  monthly_memo_count: number;
  risk_warning_count: number;
  metrics: { label: string; value: string }[];
  top_positions: {
    ticker: string;
    name: string;
    asset_class: string;
    market_value: string;
    portfolio_weight_pct: string;
    unrealized_pnl: string;
  }[];
  recent_memos: {
    ticker: string;
    memo_date: string;
    classification: string;
    action: string | null;
    composite_score: string | null;
  }[];
  risk_warnings: string[];
  model_registry_summary: { label: string; value: string }[];
  commentary: string;
};

export type RiskPolicyLimit = {
  key: string;
  label: string;
  threshold_value: string;
  unit: string;
  scope: string;
  severity: string;
  direction: string;
  description: string;
};

export type RiskPolicy = {
  name: string;
  version: string;
  status: string;
  hierarchy: string[];
  limits: RiskPolicyLimit[];
};

export type RiskPosition = {
  instrument_id: string | null;
  ticker: string;
  name: string;
  asset_class: string;
  sector: string | null;
  quantity: string;
  average_cost: string;
  market_value: string;
  unrealized_pnl: string;
  weight_pct: string;
  volatility_pct: string | null;
  beta_to_benchmark: string | null;
  liquidity_days: string | null;
};

export type RiskMeasurement = {
  key: string;
  name: string;
  measurement_type: string;
  value: string | null;
  unit: string;
  threshold_value: string | null;
  passed: boolean;
  severity: string;
  message: string;
};

export type RiskExposureBucket = {
  name: string;
  exposure_pct: string;
  market_value: string;
};

export type RiskSnapshot = {
  snapshot_id: string | null;
  portfolio_id: string;
  portfolio_name: string;
  calculated_at: string;
  as_of_date: string;
  nav: string;
  cash_balance: string;
  invested_value: string;
  cash_pct: string;
  gross_exposure_pct: string;
  net_exposure_pct: string;
  top_position_pct: string;
  top5_concentration_pct: string;
  portfolio_volatility_pct: string | null;
  beta_to_benchmark: string | null;
  max_drawdown_pct: string | null;
  var_95_pct: string | null;
  expected_shortfall_95_pct: string | null;
  liquidity_days: string | null;
  risk_level: string;
  risk_level_label: string;
};

export type StressTestResult = {
  scenario_name: string;
  scenario_type: string;
  nav_before: string;
  nav_after: string;
  nav_impact: string;
  nav_impact_pct: string;
  severity: string;
  worst_positions: {
    ticker: string;
    shock_pct: string;
    impact: string;
    impact_pct_nav: string;
  }[];
  notes: string[];
};

export type CorrelationPair = {
  ticker_a: string;
  ticker_b: string;
  correlation: string;
};

export type RiskCentreOverview = {
  snapshot: RiskSnapshot;
  policy: RiskPolicy;
  positions: RiskPosition[];
  measurements: RiskMeasurement[];
  stress_tests: StressTestResult[];
  correlation_pairs: CorrelationPair[];
  asset_class_exposure: RiskExposureBucket[];
  sector_exposure: RiskExposureBucket[];
  notes: string[];
};

export type RiskSnapshotCapture = {
  snapshot_id: string;
  captured_at: string;
  measurement_count: number;
  position_count: number;
  stress_result_count: number;
};

export type StressScenarioInput = {
  name: string;
  market_shock_pct: string;
  sector_shocks_pct?: Record<string, string>;
  ticker_shocks_pct?: Record<string, string>;
  cash_shock_pct?: string;
  notes?: string;
};

export type PreTradeRiskInput = {
  instrument: ManualTradeInput["instrument"];
  side: "buy" | "sell";
  quantity: string;
  price: string;
  fees: string;
  rationale?: string;
};

export type PreTradeRiskCheck = {
  decision: string;
  risk_level: string;
  cash_impact: string;
  pro_forma_snapshot: RiskSnapshot;
  checks: RiskMeasurement[];
  stress_tests: StressTestResult[];
  messages: string[];
};

export type StrategyPodSignal = {
  key: string;
  label: string;
  value: string;
  status: string;
  detail: string | null;
  as_of_date: string | null;
};

export type StrategyPodLatestSnapshot = {
  snapshot_id: string;
  captured_at: string;
  as_of_date: string;
  current_signal_score: string | null;
  model_confidence: string | null;
  risk_level: string;
  allocation_recommendation: string;
};

export type StrategyPod = {
  id: string;
  code: string;
  name: string;
  mandate: string;
  status: string;
  lifecycle_stage: string;
  capital_allocation_pct: string;
  risk_budget_pct: string;
  volatility_target_pct: string | null;
  max_drawdown_pct: string | null;
  turnover_ceiling_pct: string | null;
  approved_instruments: string[];
  shutdown_criteria: string | null;
  notes: string | null;
  current_signals: Record<string, unknown>;
  evaluation: Record<string, unknown>;
  live_signals: StrategyPodSignal[];
  current_signal_score: string | null;
  model_confidence: string | null;
  risk_level: string;
  allocation_recommendation: string;
  open_risk_warnings: string[];
  latest_snapshot: StrategyPodLatestSnapshot | null;
};

export type StrategyPodsOverview = {
  generated_at: string;
  portfolio_name: string;
  nav: string;
  risk_level: string;
  allocation_total_pct: string;
  risk_budget_total_pct: string;
  unallocated_pct: string;
  pods: StrategyPod[];
  warnings: string[];
};

export type StrategyPodUpdateInput = {
  status?: string;
  lifecycle_stage?: string;
  capital_allocation_pct?: string;
  risk_budget_pct?: string;
  volatility_target_pct?: string | null;
  max_drawdown_pct?: string | null;
  turnover_ceiling_pct?: string | null;
  approved_instruments?: string[];
  shutdown_criteria?: string | null;
  notes?: string | null;
};

export type StrategyPodSnapshot = {
  snapshot_id: string;
  strategy_pod_id: string;
  code: string;
  captured_at: string;
  as_of_date: string;
  status: string;
  lifecycle_stage: string;
  capital_allocation_pct: string;
  risk_budget_pct: string;
  current_signal_score: string | null;
  model_confidence: string | null;
  risk_level: string;
  allocation_recommendation: string;
};

export function getOperatingCoreDashboard(options?: ApiRequestOptions) {
  return fetchApi<OperatingCoreDashboard>("/api/operating-core/dashboard", options);
}

export function getCashLedgerHistory(options?: ApiRequestOptions) {
  return fetchApi<CashLedgerEntry[]>("/api/operating-core/cash-ledger/history", options);
}

export function createManualTrade(payload: ManualTradeInput) {
  return postApi<Trade, ManualTradeInput>("/api/operating-core/trades", payload);
}

export function getRecentTickerMemos(options?: ApiRequestOptions) {
  return fetchApi<TickerMemoSummary[]>("/api/ticker-intelligence/memos", options);
}

export function getTickerMemo(memoId: string) {
  return fetchApi<TickerMemo>(
    `/api/ticker-intelligence/memos/${encodeURIComponent(memoId)}`,
  );
}

export function getTickerPrefill(ticker: string, market?: string) {
  const marketQuery =
    market && market !== "auto" ? `?market=${encodeURIComponent(market)}` : "";
  return fetchApi<TickerPrefill>(
    `/api/ticker-intelligence/${encodeURIComponent(ticker)}/prefill${marketQuery}`,
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

export function getTickerMLReport(ticker: string, horizonDays = 63) {
  return fetchApi<TickerMLReport>(
    `/api/ticker-intelligence/ml/report/${encodeURIComponent(ticker)}?horizon_days=${horizonDays}`,
  );
}

export function getPredictiveModelComparison() {
  return fetchApi<ModelComparisonRow[]>("/api/ticker-intelligence/ml/models");
}

export function getLatestRegimeModel() {
  return fetchApi<RegimeModel>("/api/ticker-intelligence/ml/regime/latest");
}

export function createFactorBacktest(payload: BacktestRunInput) {
  return postApi<BacktestRun, BacktestRunInput>(
    "/api/ticker-intelligence/ml/backtests/factor",
    payload,
  );
}

export function getCurrentMonthlyReport(options?: ApiRequestOptions) {
  return fetchApi<MonthlyReport>("/api/reports/monthly", options);
}

export function getRiskCentreOverview(options?: ApiRequestOptions) {
  return fetchApi<RiskCentreOverview>("/api/risk-centre/overview", options);
}

export function captureRiskSnapshot() {
  return postApi<RiskSnapshotCapture, Record<string, never>>(
    "/api/risk-centre/snapshots",
    {},
  );
}

export function createCustomStressTest(payload: StressScenarioInput) {
  return postApi<StressTestResult, StressScenarioInput>(
    "/api/risk-centre/stress-tests",
    payload,
  );
}

export function createPreTradeRiskCheck(payload: PreTradeRiskInput) {
  return postApi<PreTradeRiskCheck, PreTradeRiskInput>(
    "/api/risk-centre/pre-trade-check",
    payload,
  );
}

export function getStrategyPods(options?: ApiRequestOptions) {
  return fetchApi<StrategyPodsOverview>("/api/strategy-pods", options);
}

export function getStrategyPod(code: string) {
  return fetchApi<StrategyPod>(`/api/strategy-pods/${encodeURIComponent(code)}`);
}

export function updateStrategyPod(code: string, payload: StrategyPodUpdateInput) {
  return fetch(`${API_BASE_URL}/api/strategy-pods/${encodeURIComponent(code)}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  }).then(async (response) => {
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
    return response.json() as Promise<StrategyPod>;
  });
}

export function captureStrategyPodSnapshot(code: string) {
  return postApi<StrategyPodSnapshot, Record<string, never>>(
    `/api/strategy-pods/${encodeURIComponent(code)}/snapshots`,
    {},
  );
}
