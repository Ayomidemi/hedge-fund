from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.operating_core import InstrumentCreate


class RiskPolicyLimitResponse(BaseModel):
    key: str
    label: str
    threshold_value: Decimal
    unit: str
    scope: str
    severity: str
    direction: str
    description: str


class RiskPolicyResponse(BaseModel):
    name: str
    version: str
    status: str
    hierarchy: list[str]
    limits: list[RiskPolicyLimitResponse]


class RiskExposureBucketResponse(BaseModel):
    name: str
    exposure_pct: Decimal
    market_value: Decimal


class RiskPositionResponse(BaseModel):
    instrument_id: UUID | None = None
    ticker: str
    name: str
    asset_class: str
    sector: str | None = None
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    weight_pct: Decimal
    volatility_pct: Decimal | None = None
    beta_to_benchmark: Decimal | None = None
    liquidity_days: Decimal | None = None


class RiskMeasurementResponse(BaseModel):
    key: str
    name: str
    measurement_type: str
    value: Decimal | None = None
    unit: str
    threshold_value: Decimal | None = None
    passed: bool
    severity: str
    message: str


class CorrelationPairResponse(BaseModel):
    ticker_a: str
    ticker_b: str
    correlation: Decimal


class StressScenarioCreate(BaseModel):
    name: str = Field(default="Custom scenario", min_length=1, max_length=128)
    market_shock_pct: Decimal = Decimal("0")
    sector_shocks_pct: dict[str, Decimal] = Field(default_factory=dict)
    ticker_shocks_pct: dict[str, Decimal] = Field(default_factory=dict)
    cash_shock_pct: Decimal = Decimal("0")
    notes: str | None = None


class StressTestResultResponse(BaseModel):
    scenario_name: str
    scenario_type: str
    nav_before: Decimal
    nav_after: Decimal
    nav_impact: Decimal
    nav_impact_pct: Decimal
    severity: str
    worst_positions: list[dict]
    notes: list[str] = Field(default_factory=list)


class RiskSnapshotResponse(BaseModel):
    snapshot_id: UUID | None = None
    portfolio_id: UUID
    portfolio_name: str
    calculated_at: datetime
    as_of_date: date
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    cash_pct: Decimal
    gross_exposure_pct: Decimal
    net_exposure_pct: Decimal
    top_position_pct: Decimal
    top5_concentration_pct: Decimal
    portfolio_volatility_pct: Decimal | None = None
    beta_to_benchmark: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    var_95_pct: Decimal | None = None
    expected_shortfall_95_pct: Decimal | None = None
    liquidity_days: Decimal | None = None
    risk_level: str
    risk_level_label: str


class RiskCentreOverviewResponse(BaseModel):
    snapshot: RiskSnapshotResponse
    policy: RiskPolicyResponse
    positions: list[RiskPositionResponse]
    measurements: list[RiskMeasurementResponse]
    stress_tests: list[StressTestResultResponse]
    correlation_pairs: list[CorrelationPairResponse]
    asset_class_exposure: list[RiskExposureBucketResponse]
    sector_exposure: list[RiskExposureBucketResponse]
    notes: list[str] = Field(default_factory=list)


class RiskSnapshotCaptureResponse(BaseModel):
    snapshot_id: UUID
    captured_at: datetime
    measurement_count: int
    position_count: int
    stress_result_count: int


class PreTradeRiskCheckCreate(BaseModel):
    instrument: InstrumentCreate
    side: str = Field(pattern="^(buy|sell)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    trade_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str | None = None


class PreTradeRiskCheckResponse(BaseModel):
    id: UUID
    decision: str
    risk_level: str
    cash_impact: Decimal
    pro_forma_snapshot: RiskSnapshotResponse
    checks: list[RiskMeasurementResponse]
    stress_tests: list[StressTestResultResponse]
    messages: list[str] = Field(default_factory=list)
