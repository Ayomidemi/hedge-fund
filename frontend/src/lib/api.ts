export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ApiRequestOptions = {
  accessToken?: string;
};

type ErrorResponse = {
  detail?: string | { msg?: string }[];
};

async function resolveAccessToken(
  explicit?: string,
): Promise<string | undefined> {
  if (explicit?.trim()) {
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

async function errorMessageFromResponse(response: Response) {
  let detail = `Request failed (${response.status})`;
  try {
    const body = (await response.json()) as ErrorResponse;
    if (typeof body.detail === "string") {
      detail = body.detail;
    } else if (Array.isArray(body.detail) && body.detail[0]?.msg) {
      detail = body.detail[0].msg;
    }
  } catch {
    // keep default message
  }
  return detail;
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
    throw new Error(await errorMessageFromResponse(response));
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
    throw new Error(await errorMessageFromResponse(response));
  }

  return response.json() as Promise<TResponse>;
}

async function patchApi<TResponse, TPayload>(
  path: string,
  payload: TPayload,
  options?: ApiRequestOptions,
): Promise<TResponse> {
  const accessToken = await resolveAccessToken(options?.accessToken);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      ...buildAuthHeaders(accessToken),
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(await errorMessageFromResponse(response));
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

export type TradeJournalEntry = Trade & {
  notional_value: string;
  cash_impact: string;
  fees_in_base: string;
  fee_bps: string | null;
  has_risk_notes: boolean;
};

export type TradeJournalSummary = {
  total_trades: number;
  buy_count: number;
  sell_count: number;
  unique_tickers: number;
  gross_traded_value: string;
  net_cash_impact: string;
  total_fees: string;
  average_fee_bps: string | null;
  last_trade_at: string | null;
};

export type TradeJournal = {
  portfolio: Portfolio;
  summary: TradeJournalSummary;
  trades: TradeJournalEntry[];
};

export type OpportunityStatus =
  | "discovered"
  | "screening"
  | "research"
  | "watchlist"
  | "candidate"
  | "approved"
  | "active_position"
  | "exited"
  | "post_mortem"
  | "rejected";

export type OpportunityPriority = "low" | "medium" | "high" | "urgent";

export type Opportunity = {
  id: string;
  instrument: Instrument;
  source_memo_id: string | null;
  source_recommendation_id: string | null;
  discovered_at: string;
  status: OpportunityStatus;
  priority: OpportunityPriority;
  thesis: string;
  research_question: string | null;
  next_action: string | null;
  time_horizon: string | null;
  conviction_score: string | null;
  expected_edge_pct: string | null;
  target_weight: string | null;
  review_by: string | null;
  closed_at: string | null;
  notes: string | null;
  status_history: Record<string, unknown>[];
  latest_action: string | null;
  latest_composite_score: string | null;
  latest_confidence_score: string | null;
  created_at: string;
  updated_at: string;
};

export type OpportunityCandidate = {
  memo_id: string;
  recommendation_id: string | null;
  ticker: string;
  name: string;
  asset_class: string;
  memo_date: string;
  classification: string;
  executive_view: string;
  action: string | null;
  composite_score: string | null;
  confidence_score: string | null;
};

export type OpportunityQueueSummary = {
  total: number;
  active: number;
  high_priority: number;
  approved: number;
  candidates: number;
  next_review_by: string | null;
  status_counts: Record<string, number>;
};

export type OpportunityQueue = {
  generated_at: string;
  summary: OpportunityQueueSummary;
  opportunities: Opportunity[];
  candidates: OpportunityCandidate[];
  status_order: OpportunityStatus[];
};

export type OpportunityCreateInput = {
  source_memo_id?: string;
  instrument?: ManualTradeInput["instrument"];
  status?: OpportunityStatus;
  priority?: OpportunityPriority;
  thesis?: string;
  research_question?: string;
  next_action?: string;
  time_horizon?: string;
  conviction_score?: string;
  expected_edge_pct?: string;
  target_weight?: string;
  review_by?: string;
  notes?: string;
};

export type OpportunityUpdateInput = Partial<Omit<OpportunityCreateInput, "source_memo_id" | "instrument">>;

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
  prices_as_of: string | null;
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

export function createCashDeposit(payload: CashMovementInput, options?: ApiRequestOptions) {
  return postApi<CashLedgerEntry, CashMovementInput>(
    "/api/operating-core/cash-ledger/deposits",
    payload,
    options,
  );
}

export function createCashWithdrawal(payload: CashMovementInput, options?: ApiRequestOptions) {
  return postApi<CashLedgerEntry, CashMovementInput>(
    "/api/operating-core/cash-ledger/withdrawals",
    payload,
    options,
  );
}

export function createCashAdjustment(
  payload: CashMovementInput & { description: string },
  options?: ApiRequestOptions,
) {
  return postApi<CashLedgerEntry, CashMovementInput & { description: string }>(
    "/api/operating-core/cash-ledger/adjustments",
    payload,
    options,
  );
}

export function createCashLedgerEntry(
  payload: CashLedgerEntryInput,
  options?: ApiRequestOptions,
) {
  return createCashDeposit(payload, options);
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
  trade_date?: string;
  rationale?: string;
  risk_notes?: string;
  broker_reference?: string;
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

export type TickerSuggestion = TickerPrefill["instrument"];

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

export type AttributionSummary = {
  portfolio_id: string;
  portfolio_name: string;
  generated_at: string;
  period_start: string | null;
  period_end: string;
  nav: string;
  cash_balance: string;
  invested_value: string;
  net_external_flow: string;
  total_deposits: string;
  total_withdrawals: string;
  gross_traded_value: string;
  total_fees: string;
  gross_realized_pnl: string;
  unrealized_pnl: string;
  net_pnl: string;
  portfolio_pnl_from_nav: string;
  reconciliation_gap: string;
  total_return_pct: string;
  fee_drag_pct: string;
  turnover_pct: string;
  hit_rate_pct: string | null;
  profit_factor: string | null;
  trade_count: number;
  closed_trade_count: number;
  winning_trade_count: number;
  losing_trade_count: number;
};

export type AttributionRow = {
  instrument: Instrument;
  status: string;
  quantity: string;
  average_cost: string;
  market_value: string;
  portfolio_weight_pct: string;
  gross_buys: string;
  gross_sells: string;
  gross_realized_pnl: string;
  unrealized_pnl: string;
  fees: string;
  net_pnl: string;
  contribution_pct_nav: string;
  return_on_traded_capital_pct: string;
  trade_count: number;
  closed_trade_count: number;
  win_rate_pct: string | null;
};

export type AttributionBucket = {
  name: string;
  exposure_pct: string;
  market_value: string;
  gross_traded_value: string;
  gross_realized_pnl: string;
  unrealized_pnl: string;
  fees: string;
  net_pnl: string;
  contribution_pct_nav: string;
  instrument_count: number;
};

export type AttributionRealizedEvent = {
  trade_id: string;
  trade_date: string;
  instrument: Instrument;
  quantity: string;
  exit_price: string;
  average_cost: string;
  gross_realized_pnl: string;
  fees: string;
  net_realized_pnl: string;
  return_pct: string;
};

export type AttributionReport = {
  summary: AttributionSummary;
  by_ticker: AttributionRow[];
  by_asset_class: AttributionBucket[];
  by_sector: AttributionBucket[];
  realized_events: AttributionRealizedEvent[];
  notes: string[];
};

export type ResearchLabSummary = {
  portfolio_name: string;
  nav: string;
  research_memo_count: number;
  active_opportunity_count: number;
  dataset_count: number;
  feature_set_count: number;
  model_count: number;
  backtest_count: number;
  warning_count: number;
};

export type ResearchPipelineStage = {
  key: string;
  label: string;
  count: number;
  description: string;
};

export type ResearchDataset = {
  key: string;
  name: string;
  source: string;
  row_count: number;
  instrument_count: number;
  latest_observation: string | null;
  frequency: string;
  status: string;
  validation_summary: string;
};

export type ResearchFeatureSet = {
  feature_version: string;
  snapshot_count: number;
  instrument_count: number;
  feature_count: number;
  first_as_of_date: string | null;
  last_as_of_date: string | null;
  average_quality_score: string | null;
  status: string;
  notes: string;
};

export type ResearchNotebook = {
  id: string;
  title: string;
  ticker: string;
  classification: string;
  memo_date: string;
  status: string;
  linked_recommendation_id: string | null;
  summary: string;
};

export type ResearchExperiment = {
  id: string;
  name: string;
  experiment_type: string;
  status: string;
  hypothesis: string;
  feature_version: string | null;
  horizon_days: number | null;
  validation_metric: string | null;
  validation_value: string | null;
  created_at: string;
};

export type ResearchBacktest = {
  id: string;
  name: string;
  status: string;
  strategy: string;
  benchmark: string | null;
  cost_model: string;
  latest_run_at: string | null;
  primary_metric: string | null;
  notes: string;
};

export type ResearchModel = {
  model_version_id: string;
  model_name: string;
  model_version: string;
  purpose: string;
  feature_version: string | null;
  horizon_days: number | null;
  training_rows: number | null;
  validation_rows: number | null;
  validation_directional_accuracy: string | null;
  validation_r2: string | null;
  status: string;
  created_at: string;
};

export type ResearchValidationCheck = {
  key: string;
  label: string;
  status: string;
  detail: string;
};

export type ResearchActionItem = {
  key: string;
  label: string;
  priority: string;
  owner_area: string;
  detail: string;
  action_path: string | null;
};

export type ResearchLabOverview = {
  generated_at: string;
  summary: ResearchLabSummary;
  pipeline: ResearchPipelineStage[];
  datasets: ResearchDataset[];
  feature_sets: ResearchFeatureSet[];
  notebooks: ResearchNotebook[];
  experiments: ResearchExperiment[];
  backtests: ResearchBacktest[];
  models: ResearchModel[];
  validation_checks: ResearchValidationCheck[];
  action_items: ResearchActionItem[];
  notes: string[];
};

export type ResearchPipelineRunInput = {
  tickers: string[];
  benchmark_ticker?: string;
  start_date: string;
  end_date?: string;
  horizon_days?: number;
  source?: string;
  train_model?: boolean;
};

export type ResearchPipelineRunStep = {
  name: string;
  status: string;
  message: string;
  rows: number | null;
};

export type ResearchPipelineRun = {
  tickers: string[];
  benchmark_ticker: string;
  start_date: string;
  end_date: string;
  horizon_days: number;
  steps: ResearchPipelineRunStep[];
  model_version_id: string | null;
  warnings: string[];
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

export function createManualTrade(payload: ManualTradeInput, options?: ApiRequestOptions) {
  return postApi<Trade, ManualTradeInput>("/api/operating-core/trades", payload, options);
}

export function updateManualTrade(
  tradeId: string,
  payload: ManualTradeInput,
  options?: ApiRequestOptions,
) {
  return patchApi<Trade, ManualTradeInput>(
    `/api/operating-core/trades/${encodeURIComponent(tradeId)}`,
    payload,
    options,
  );
}

export function getTradeJournal(options?: ApiRequestOptions) {
  return fetchApi<TradeJournal>("/api/operating-core/trades", options);
}

export function getOpportunityQueue(options?: ApiRequestOptions) {
  return fetchApi<OpportunityQueue>("/api/opportunity-queue", options);
}

export function createOpportunity(
  payload: OpportunityCreateInput,
  options?: ApiRequestOptions,
) {
  return postApi<Opportunity, OpportunityCreateInput>(
    "/api/opportunity-queue",
    payload,
    options,
  );
}

export function updateOpportunity(
  opportunityId: string,
  payload: OpportunityUpdateInput,
  options?: ApiRequestOptions,
) {
  return patchApi<Opportunity, OpportunityUpdateInput>(
    `/api/opportunity-queue/${encodeURIComponent(opportunityId)}`,
    payload,
    options,
  );
}

export function getRecentTickerMemos(options?: ApiRequestOptions) {
  return fetchApi<TickerMemoSummary[]>("/api/ticker-intelligence/memos", options);
}

export function getTickerMemo(memoId: string, options?: ApiRequestOptions) {
  return fetchApi<TickerMemo>(
    `/api/ticker-intelligence/memos/${encodeURIComponent(memoId)}`,
    options,
  );
}

export function getTickerPrefill(
  ticker: string,
  market?: string,
  options?: ApiRequestOptions,
) {
  const marketQuery =
    market && market !== "auto" ? `?market=${encodeURIComponent(market)}` : "";
  return fetchApi<TickerPrefill>(
    `/api/ticker-intelligence/${encodeURIComponent(ticker)}/prefill${marketQuery}`,
    options,
  );
}

export function getTickerSuggestions(
  query: string,
  limit = 8,
  options?: ApiRequestOptions,
) {
  const search = new URLSearchParams({ query, limit: String(limit) });
  return fetchApi<TickerSuggestion[]>(
    `/api/ticker-intelligence/suggestions?${search.toString()}`,
    options,
  );
}

export function createTickerAIDraft(
  payload: TickerAIDraftInput,
  options?: ApiRequestOptions,
) {
  return postApi<TickerAIDraft, TickerAIDraftInput>(
    "/api/ticker-intelligence/ai/draft",
    payload,
    options,
  );
}

export function createTickerAnalysis(
  payload: TickerAnalysisInput,
  options?: ApiRequestOptions,
) {
  return postApi<TickerAnalysis, TickerAnalysisInput>(
    "/api/ticker-intelligence/analyze",
    payload,
    options,
  );
}

export function getTickerMLReport(
  ticker: string,
  horizonDays = 63,
  options?: ApiRequestOptions,
) {
  return fetchApi<TickerMLReport>(
    `/api/ticker-intelligence/ml/report/${encodeURIComponent(ticker)}?horizon_days=${horizonDays}`,
    options,
  );
}

export function getPredictiveModelComparison(options?: ApiRequestOptions) {
  return fetchApi<ModelComparisonRow[]>("/api/ticker-intelligence/ml/models", options);
}

export function getLatestRegimeModel(options?: ApiRequestOptions) {
  return fetchApi<RegimeModel>("/api/ticker-intelligence/ml/regime/latest", options);
}

export function createFactorBacktest(payload: BacktestRunInput, options?: ApiRequestOptions) {
  return postApi<BacktestRun, BacktestRunInput>(
    "/api/ticker-intelligence/ml/backtests/factor",
    payload,
    options,
  );
}

export type RegimeModelFitInput = {
  ticker?: string;
  source?: string;
  state_count?: number;
  lookback_days?: number;
};

export function fitRegimeModel(payload: RegimeModelFitInput, options?: ApiRequestOptions) {
  return postApi<RegimeModel, RegimeModelFitInput>(
    "/api/ticker-intelligence/ml/regime/hmm",
    payload,
    options,
  );
}

export type YahooPriceBackfillInput = {
  ticker: string;
  start_date: string;
  end_date?: string;
  name?: string;
  asset_class?: string;
  exchange?: string;
  currency?: string;
  yahoo_symbol?: string;
};

export type PriceBackfillResult = {
  ticker: string;
  source: string;
  start_date: string;
  end_date: string;
  rows_fetched: number;
  rows_saved: number;
};

export type TrainingLabelGenerateInput = {
  ticker: string;
  benchmark_ticker?: string;
  horizons?: number[];
  source?: string;
};

export type TrainingLabelResult = {
  ticker: string;
  benchmark_ticker: string | null;
  horizons: number[];
  labels_generated: number;
  first_as_of_date: string | null;
  last_as_of_date: string | null;
};

export type PriceFeatureBuildInput = {
  tickers: string[];
  source?: string;
  feature_version?: string;
};

export type PriceFeatureBuildResult = {
  feature_version: string;
  source: string;
  tickers: string[];
  snapshots_saved: number;
  first_as_of_date: string | null;
  last_as_of_date: string | null;
};

export type PredictiveModelTrainInput = {
  tickers: string[];
  horizon_days?: number;
  benchmark_ticker?: string;
  feature_version?: string;
  label_source?: string;
  ridge_alpha?: string;
};

export type PredictiveModelTrainResult = {
  model_version_id: string;
  model_name: string;
  model_version: string;
  horizon_days: number;
  feature_version: string;
  training_rows: number;
  validation_rows: number;
  feature_names: string[];
  metrics: Record<string, unknown>;
};

export function backfillYahooPrices(
  payload: YahooPriceBackfillInput,
  options?: ApiRequestOptions,
) {
  return postApi<PriceBackfillResult, YahooPriceBackfillInput>(
    "/api/ticker-intelligence/ml/prices/yahoo/backfill",
    payload,
    options,
  );
}

export function generateTrainingLabels(
  payload: TrainingLabelGenerateInput,
  options?: ApiRequestOptions,
) {
  return postApi<TrainingLabelResult, TrainingLabelGenerateInput>(
    "/api/ticker-intelligence/ml/labels",
    payload,
    options,
  );
}

export function buildPriceFeatures(payload: PriceFeatureBuildInput, options?: ApiRequestOptions) {
  return postApi<PriceFeatureBuildResult, PriceFeatureBuildInput>(
    "/api/ticker-intelligence/ml/features/price",
    payload,
    options,
  );
}

export function trainPredictiveModel(
  payload: PredictiveModelTrainInput,
  options?: ApiRequestOptions,
) {
  return postApi<PredictiveModelTrainResult, PredictiveModelTrainInput>(
    "/api/ticker-intelligence/ml/train",
    payload,
    options,
  );
}

export function getCurrentMonthlyReport(options?: ApiRequestOptions) {
  return fetchApi<MonthlyReport>("/api/reports/monthly", options);
}

export function getAttributionReport(options?: ApiRequestOptions) {
  return fetchApi<AttributionReport>("/api/attribution/overview", options);
}

export function getResearchLabOverview(options?: ApiRequestOptions) {
  return fetchApi<ResearchLabOverview>("/api/research-lab/overview", options);
}

export function runResearchDataPipeline(
  payload: ResearchPipelineRunInput,
  options?: ApiRequestOptions,
) {
  return postApi<ResearchPipelineRun, ResearchPipelineRunInput>(
    "/api/ticker-intelligence/ml/pipeline/run",
    payload,
    options,
  );
}

export function getRiskCentreOverview(options?: ApiRequestOptions) {
  return fetchApi<RiskCentreOverview>("/api/risk-centre/overview", options);
}

export function captureRiskSnapshot(options?: ApiRequestOptions) {
  return postApi<RiskSnapshotCapture, Record<string, never>>(
    "/api/risk-centre/snapshots",
    {},
    options,
  );
}

export function createCustomStressTest(
  payload: StressScenarioInput,
  options?: ApiRequestOptions,
) {
  return postApi<StressTestResult, StressScenarioInput>(
    "/api/risk-centre/stress-tests",
    payload,
    options,
  );
}

export function createPreTradeRiskCheck(
  payload: PreTradeRiskInput,
  options?: ApiRequestOptions,
) {
  return postApi<PreTradeRiskCheck, PreTradeRiskInput>(
    "/api/risk-centre/pre-trade-check",
    payload,
    options,
  );
}

export function getStrategyPods(options?: ApiRequestOptions) {
  return fetchApi<StrategyPodsOverview>("/api/strategy-pods", options);
}

export function getStrategyPod(code: string, options?: ApiRequestOptions) {
  return fetchApi<StrategyPod>(
    `/api/strategy-pods/${encodeURIComponent(code)}`,
    options,
  );
}

export function updateStrategyPod(
  code: string,
  payload: StrategyPodUpdateInput,
  options?: ApiRequestOptions,
) {
  return patchApi<StrategyPod, StrategyPodUpdateInput>(
    `/api/strategy-pods/${encodeURIComponent(code)}`,
    payload,
    options,
  );
}

export function getStrategyPodSnapshots(code: string, options?: ApiRequestOptions) {
  return fetchApi<StrategyPodSnapshot[]>(
    `/api/strategy-pods/${encodeURIComponent(code)}/snapshots`,
    options,
  );
}

export function captureStrategyPodSnapshot(code: string, options?: ApiRequestOptions) {
  return postApi<StrategyPodSnapshot, Record<string, never>>(
    `/api/strategy-pods/${encodeURIComponent(code)}/snapshots`,
    {},
    options,
  );
}

export type SystemLogEntry = {
  id: string;
  level: string;
  category: string;
  event: string;
  message: string;
  context: Record<string, unknown>;
  created_at: string;
};

export type AdministrationModelVersion = {
  id: string;
  name: string;
  version: string;
  pod: string;
  purpose: string;
  approved_use: string | null;
  shutdown_criteria: string | null;
  validation_status: string;
  created_at: string;
};

export type AdministrationDataVersion = {
  key: string;
  label: string;
  record_count: number;
  instrument_count: number;
  latest_as_of_date: string | null;
};

export type AdministrationPortfolioRule = {
  name: string;
  limit_type: string;
  threshold_value: string;
  unit: string;
  scope: string;
};

export type AdministrationRiskPolicy = {
  id: string;
  name: string;
  version: string;
  status: string;
  effective_at: string;
  limit_count: number;
  notes: string | null;
};

export type PriceRefreshRun = {
  id: string;
  started_at: string;
  finished_at: string | null;
  status: string;
  ticker_count: number;
  success_count: number;
  failure_count: number;
  positions_marked: number;
  interval_seconds: number;
  errors: Array<{ ticker?: string; error: string }>;
};

export type FxRateSnapshot = {
  base_currency: string;
  quote_currency: string;
  rate: string;
  source: string;
  as_of: string;
  is_stale: boolean;
};

export type SystemLogList = {
  items: SystemLogEntry[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

export type AdministrationOverview = {
  generated_at: string;
  portfolio_name: string;
  system_logs: SystemLogEntry[];
  system_log_total: number;
  model_versions: AdministrationModelVersion[];
  data_versions: AdministrationDataVersion[];
  portfolio_rules: AdministrationPortfolioRule[];
  risk_policies: AdministrationRiskPolicy[];
  price_refresh_runs: PriceRefreshRun[];
  latest_fx_rate: FxRateSnapshot | null;
};

export function getAdministrationOverview(
  params?: { log_limit?: number; log_category?: string },
  options?: ApiRequestOptions,
) {
  const search = new URLSearchParams();
  if (params?.log_limit) search.set("log_limit", String(params.log_limit));
  if (params?.log_category && params.log_category !== "all") {
    search.set("log_category", params.log_category);
  }
  const query = search.toString();
  return fetchApi<AdministrationOverview>(
    `/api/administration/overview${query ? `?${query}` : ""}`,
    options,
  );
}

export function getAdministrationLogs(
  params?: { page?: number; page_size?: number; log_category?: string },
  options?: ApiRequestOptions,
) {
  const search = new URLSearchParams();
  if (params?.page) search.set("page", String(params.page));
  if (params?.page_size) search.set("page_size", String(params.page_size));
  if (params?.log_category && params.log_category !== "all") {
    search.set("log_category", params.log_category);
  }
  const query = search.toString();
  return fetchApi<SystemLogList>(
    `/api/administration/logs${query ? `?${query}` : ""}`,
    options,
  );
}
