export type LabSection =
  | "overview"
  | "notebooks"
  | "datasets"
  | "features"
  | "experiments"
  | "backtests"
  | "models";

export type PipelineStage = {
  id: string;
  label: string;
  count: number;
};

export type NotebookItem = {
  id: string;
  name: string;
  owner: string;
  lastEdited: string;
  linkedExperiment: string | null;
  status: "idle" | "running" | "dirty";
};

export type DatasetItem = {
  id: string;
  name: string;
  source: string;
  records: string;
  frequency: string;
  version: string;
  updated: string;
  validation: "passed" | "warnings" | "failed";
};

export type FeatureItem = {
  id: string;
  name: string;
  version: string;
  category: string;
  usedBy: number;
  updated: string;
};

export type ExperimentItem = {
  id: string;
  name: string;
  hypothesis: string;
  owner: string;
  modelType: string;
  status: "running" | "complete" | "failed" | "draft";
  sharpe: string | null;
  created: string;
};

export type BacktestItem = {
  id: string;
  name: string;
  strategy: string;
  period: string;
  sharpe: string;
  maxDrawdown: string;
  benchmarkAlpha: string;
  walkForward: boolean;
  costsIncluded: boolean;
  status: "passed" | "review" | "failed";
};

export type ModelItem = {
  id: string;
  name: string;
  version: string;
  purpose: string;
  owner: string;
  stage: "research" | "validated" | "paper" | "production" | "retired";
  sharpe: string;
  oosSharpe: string;
  validationsPassed: number;
  validationsTotal: number;
  confidence: "high" | "medium" | "low";
};

export const pipelineStages: PipelineStage[] = [
  { id: "research", label: "Research", count: 8 },
  { id: "validated", label: "Validated", count: 3 },
  { id: "paper", label: "Paper trading", count: 2 },
  { id: "production", label: "Production candidate", count: 1 },
  { id: "deployed", label: "Approved", count: 1 },
];

export const labStats = [
  { label: "Active experiments", value: "6" },
  { label: "Datasets", value: "14" },
  { label: "Registered features", value: "38" },
  { label: "Models in registry", value: "11" },
];

export const notebooks: NotebookItem[] = [
  {
    id: "nb-1",
    name: "cross_asset_momentum_v2.ipynb",
    owner: "Pease",
    lastEdited: "2 hours ago",
    linkedExperiment: "exp-momentum-014",
    status: "dirty",
  },
  {
    id: "nb-2",
    name: "regime_hmm_exploration.ipynb",
    owner: "Pease",
    lastEdited: "Yesterday",
    linkedExperiment: "exp-regime-003",
    status: "idle",
  },
  {
    id: "nb-3",
    name: "equity_factor_screen.ipynb",
    owner: "Pease",
    lastEdited: "3 days ago",
    linkedExperiment: null,
    status: "running",
  },
  {
    id: "nb-4",
    name: "pairs_cointegration_scan.ipynb",
    owner: "Pease",
    lastEdited: "1 week ago",
    linkedExperiment: "exp-rv-002",
    status: "idle",
  },
];

export const datasets: DatasetItem[] = [
  {
    id: "ds-1",
    name: "us_equity_daily_ohlcv",
    source: "Market data",
    records: "4.2M",
    frequency: "Daily",
    version: "2026.08.01",
    updated: "Aug 1",
    validation: "passed",
  },
  {
    id: "ds-2",
    name: "fundamentals_point_in_time",
    source: "Corporate fundamentals",
    records: "890K",
    frequency: "Quarterly",
    version: "2026.07.28",
    updated: "Jul 28",
    validation: "passed",
  },
  {
    id: "ds-3",
    name: "macro_regime_indicators",
    source: "Macroeconomic data",
    records: "12K",
    frequency: "Monthly",
    version: "2026.08.03",
    updated: "Aug 3",
    validation: "warnings",
  },
  {
    id: "ds-4",
    name: "earnings_transcripts_nlp",
    source: "Earnings transcripts",
    records: "18K",
    frequency: "Event",
    version: "2026.06.15",
    updated: "Jun 15",
    validation: "passed",
  },
  {
    id: "ds-5",
    name: "news_sentiment_daily",
    source: "News",
    records: "1.1M",
    frequency: "Daily",
    version: "2026.07.20",
    updated: "Jul 20",
    validation: "failed",
  },
];

export const features: FeatureItem[] = [
  {
    id: "ft-1",
    name: "volatility_adjusted_momentum_12m",
    version: "1.2.0",
    category: "Momentum",
    usedBy: 4,
    updated: "Aug 2",
  },
  {
    id: "ft-2",
    name: "sector_relative_strength",
    version: "2.0.1",
    category: "Cross-sectional",
    usedBy: 3,
    updated: "Jul 30",
  },
  {
    id: "ft-3",
    name: "yield_curve_slope",
    version: "1.0.0",
    category: "Macro",
    usedBy: 2,
    updated: "Jul 25",
  },
  {
    id: "ft-4",
    name: "fcf_yield_percentile",
    version: "1.1.0",
    category: "Quality",
    usedBy: 5,
    updated: "Jul 18",
  },
  {
    id: "ft-5",
    name: "earnings_revision_score",
    version: "0.9.0",
    category: "Sentiment",
    usedBy: 1,
    updated: "Jun 28",
  },
];

export const experiments: ExperimentItem[] = [
  {
    id: "exp-momentum-014",
    name: "Cross-asset momentum — vol targeting",
    hypothesis: "Vol-scaled momentum improves Sharpe across ETF universe",
    owner: "Pease",
    modelType: "Time-series rules",
    status: "running",
    sharpe: null,
    created: "Aug 5",
  },
  {
    id: "exp-regime-003",
    name: "HMM regime classifier — 4 states",
    hypothesis: "4-state HMM separates inflation/growth regimes better than rules",
    owner: "Pease",
    modelType: "HMM",
    status: "complete",
    sharpe: "1.14",
    created: "Aug 1",
  },
  {
    id: "exp-equity-008",
    name: "Quant equity ranker — XGBoost",
    hypothesis: "Non-linear factor combo beats linear ranker OOS",
    owner: "Pease",
    modelType: "XGBoost",
    status: "complete",
    sharpe: "0.92",
    created: "Jul 28",
  },
  {
    id: "exp-rv-002",
    name: "Sector pair mean reversion",
    hypothesis: "XLK/XLF spread mean-reverts within 20-day window",
    owner: "Pease",
    modelType: "Stat arb",
    status: "failed",
    sharpe: "0.21",
    created: "Jul 20",
  },
  {
    id: "exp-trend-001",
    name: "Multi-horizon trend blend",
    hypothesis: "Blending 1m/3m/6m momentum reduces whipsaw",
    owner: "Pease",
    modelType: "Signal ensemble",
    status: "draft",
    sharpe: null,
    created: "Aug 4",
  },
];

export const backtests: BacktestItem[] = [
  {
    id: "bt-1",
    name: "Trend pod — walk-forward 2018–2025",
    strategy: "Cross-Asset Trend",
    period: "2018 – 2025",
    sharpe: "1.08",
    maxDrawdown: "−8.4%",
    benchmarkAlpha: "+2.1%",
    walkForward: true,
    costsIncluded: true,
    status: "passed",
  },
  {
    id: "bt-2",
    name: "Quant equity ranker — OOS 2022–2025",
    strategy: "Quantitative Equity",
    period: "2022 – 2025",
    sharpe: "0.87",
    maxDrawdown: "−11.2%",
    benchmarkAlpha: "+1.4%",
    walkForward: true,
    costsIncluded: true,
    status: "review",
  },
  {
    id: "bt-3",
    name: "Regime overlay — macro allocation",
    strategy: "Macro Regime",
    period: "2015 – 2025",
    sharpe: "0.74",
    maxDrawdown: "−14.6%",
    benchmarkAlpha: "+0.6%",
    walkForward: false,
    costsIncluded: true,
    status: "review",
  },
  {
    id: "bt-4",
    name: "Pairs RV — sector spreads",
    strategy: "Relative Value",
    period: "2020 – 2025",
    sharpe: "0.31",
    maxDrawdown: "−18.9%",
    benchmarkAlpha: "−0.8%",
    walkForward: true,
    costsIncluded: false,
    status: "failed",
  },
];

export const models: ModelItem[] = [
  {
    id: "mdl-1",
    name: "cross_asset_trend_v3",
    version: "3.1.0",
    purpose: "Directional signals across ETF universe",
    owner: "Pease",
    stage: "paper",
    sharpe: "1.08",
    oosSharpe: "0.96",
    validationsPassed: 8,
    validationsTotal: 9,
    confidence: "high",
  },
  {
    id: "mdl-2",
    name: "regime_hmm_4state",
    version: "1.0.0",
    purpose: "Macro regime classification",
    owner: "Pease",
    stage: "validated",
    sharpe: "0.74",
    oosSharpe: "0.68",
    validationsPassed: 7,
    validationsTotal: 9,
    confidence: "medium",
  },
  {
    id: "mdl-3",
    name: "equity_ranker_xgb",
    version: "2.4.0",
    purpose: "Cross-sectional equity ranking",
    owner: "Pease",
    stage: "research",
    sharpe: "0.92",
    oosSharpe: "0.71",
    validationsPassed: 5,
    validationsTotal: 9,
    confidence: "low",
  },
  {
    id: "mdl-4",
    name: "baseline_ma_crossover",
    version: "1.0.0",
    purpose: "Simplicity baseline for trend pod",
    owner: "System",
    stage: "production",
    sharpe: "0.55",
    oosSharpe: "0.52",
    validationsPassed: 9,
    validationsTotal: 9,
    confidence: "high",
  },
];

export const validationChecks = [
  "In-sample testing",
  "Validation testing",
  "Out-of-sample testing",
  "Walk-forward testing",
  "Cost-adjusted testing",
  "Regime testing",
  "Sensitivity analysis",
  "Stability analysis",
  "Baseline comparison",
];

export const sectionLabels: Record<LabSection, string> = {
  overview: "Overview",
  notebooks: "Notebooks",
  datasets: "Datasets",
  features: "Features",
  experiments: "Experiments",
  backtests: "Backtests",
  models: "Models",
};
