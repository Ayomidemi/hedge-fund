from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.schemas.operating_core import InstrumentCreate, InstrumentResponse


class TickerMetricsInput(BaseModel):
    current_price: Decimal | None = Field(default=None, gt=0)
    market_cap_billion: Decimal | None = Field(default=None, ge=0)
    pe_ratio: Decimal | None = Field(default=None, gt=0)
    forward_pe: Decimal | None = Field(default=None, gt=0)
    revenue_growth_pct: Decimal | None = None
    earnings_growth_pct: Decimal | None = None
    free_cash_flow_yield_pct: Decimal | None = None
    net_margin_pct: Decimal | None = None
    debt_to_equity: Decimal | None = Field(default=None, ge=0)
    price_vs_200d_pct: Decimal | None = None
    relative_strength_6m_pct: Decimal | None = None
    volatility_30d_pct: Decimal | None = Field(default=None, ge=0)


class TickerAnalysisCreate(BaseModel):
    instrument: InstrumentCreate
    metrics: TickerMetricsInput = Field(default_factory=TickerMetricsInput)
    memo_date: date = Field(default_factory=date.today)
    data_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    time_horizon: str = Field(default="6-18 months", min_length=1, max_length=64)
    investment_question: str | None = None
    thesis: str = Field(min_length=1)
    bull_case: str | None = None
    base_case: str | None = None
    bear_case: str | None = None
    thesis_breakers: str | None = None
    risk_notes: str | None = None
    source_reference: str | None = Field(default=None, max_length=512)


class TickerPrefillResponse(BaseModel):
    instrument: InstrumentCreate
    metrics: TickerMetricsInput
    provider: str
    source_reference: str
    data_timestamp: datetime
    source_warnings: list[str] = Field(default_factory=list)
    raw_sources: dict = Field(default_factory=dict)


class TickerAIDraftCreate(BaseModel):
    instrument: InstrumentCreate
    metrics: TickerMetricsInput = Field(default_factory=TickerMetricsInput)
    time_horizon: str = Field(default="6-18 months", min_length=1, max_length=64)
    source_reference: str | None = Field(default=None, max_length=512)
    source_warnings: list[str] = Field(default_factory=list)
    user_notes: str | None = None


class TickerAIDraftResponse(BaseModel):
    prompt_version: str
    model: str
    investment_question: str
    analyst_questions: list[str]
    thesis: str
    bull_case: str
    base_case: str
    bear_case: str
    thesis_breakers: str
    risk_notes: str
    missing_data_warnings: list[str]
    confidence_notes: str


class TickerScoreResponse(BaseModel):
    name: str
    score: Decimal
    weight: Decimal
    notes: str


class TickerMemoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instrument: InstrumentResponse
    recommendation_id: UUID | None
    memo_date: date
    classification: str
    time_horizon: str | None
    executive_view: str
    thesis: str
    bull_case: str | None
    base_case: str | None
    bear_case: str | None
    thesis_breakers: str | None
    risk_assessment: str | None
    scores: dict
    data_timestamp: datetime
    model_version_label: str | None


class TickerAnalysisResponse(BaseModel):
    memo: TickerMemoResponse
    action: str
    confidence_score: Decimal
    conviction_score: Decimal
    recommended_weight: Decimal
    composite_score: Decimal
    classification: str
    scorecard: list[TickerScoreResponse]
    evidence_summary: str


class TickerMemoSummaryResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    asset_class: str
    memo_date: date
    classification: str
    executive_view: str
    composite_score: Decimal | None = None
    action: str | None = None
    confidence_score: Decimal | None = None

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, value: str) -> str:
        return value.upper()


class YahooPriceBackfillCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=255)
    asset_class: str = Field(default="equity", max_length=32)
    exchange: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    yahoo_symbol: str | None = Field(default=None, max_length=64)
    start_date: date
    end_date: date = Field(default_factory=date.today)


class PriceBackfillResponse(BaseModel):
    ticker: str
    source: str
    start_date: date
    end_date: date
    rows_fetched: int
    rows_saved: int


class TrainingLabelGenerateCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    benchmark_ticker: str | None = Field(default="SPY", max_length=32)
    horizons: list[int] = Field(default_factory=lambda: [21, 63, 126])
    source: str = Field(default="yahoo", max_length=64)


class TrainingLabelResponse(BaseModel):
    ticker: str
    benchmark_ticker: str | None
    horizons: list[int]
    labels_generated: int
    first_as_of_date: date | None
    last_as_of_date: date | None


class TickerDatasetRowResponse(BaseModel):
    as_of_date: date
    feature_version: str
    features: dict
    labels: list[dict] = Field(default_factory=list)
