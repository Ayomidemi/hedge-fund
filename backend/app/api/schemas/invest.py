from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class InvestAccountResponse(BaseModel):
    id: UUID
    account_number: str
    broker_provider: str
    status: str
    base_currency: str
    cash: Decimal
    buying_power: Decimal
    created_at: datetime


class InvestHolding(BaseModel):
    ticker: str
    name: str
    asset_class: str | None = None
    currency: str
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal | None = None
    market_value: Decimal
    allocation_pct: Decimal | None = None
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None = None
    href: str | None = None


class InvestAllocationBucket(BaseModel):
    name: str
    value: Decimal
    allocation_pct: Decimal


class InvestHomeResponse(BaseModel):
    account: InvestAccountResponse
    portfolio_value: Decimal
    cash: Decimal
    invested: Decimal
    total_return: Decimal
    total_return_pct: Decimal | None = None
    today_change: Decimal | None = None
    today_change_pct: Decimal | None = None
    allocation: list[InvestAllocationBucket] = Field(default_factory=list)
    holdings: list[InvestHolding] = Field(default_factory=list)
    headlines: list[str] = Field(default_factory=list)


class InvestOrderCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    side: str = Field(min_length=3, max_length=8)
    order_type: str = "market"
    amount: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal | None = Field(default=None, gt=0)

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("side")
    @classmethod
    def normalize_side(cls, value: str) -> str:
        return value.strip().upper()


class InvestOrderResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    asset_class: str | None = None
    currency: str
    side: str
    order_type: str
    quantity: Decimal | None
    notional: Decimal | None
    status: str
    submitted_at: datetime
    filled_at: datetime | None = None
    average_fill_price: Decimal | None = None
    filled_quantity: Decimal | None = None
    broker_provider: str | None = None
    broker_order_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class InvestCashRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class InvestWatchlistCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    notes: str | None = None

    @field_validator("ticker")
    @classmethod
    def uppercase_ticker(cls, value: str) -> str:
        return value.strip().upper()


class InvestWatchlistItemResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    asset_class: str | None = None
    currency: str
    href: str
    notes: str | None = None
    date_added: datetime
    price: Decimal | None = None
    change_pct: Decimal | None = None
    headline: str | None = None
    unusual: bool = False
    unusual_label: str | None = None


class InvestInstrumentResponse(BaseModel):
    ticker: str
    name: str
    asset_class: str
    exchange: str | None = None
    currency: str
    sector: str | None = None
    industry: str | None = None
    price: Decimal | None = None


class InvestResearchMetricResponse(BaseModel):
    label: str
    value: str
    tone: str = "neutral"


class InvestResearchSectionResponse(BaseModel):
    id: str
    title: str
    summary: str
    metrics: list[InvestResearchMetricResponse] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class InvestPeaseFactorResponse(BaseModel):
    id: str
    label: str
    score: Decimal | None = None
    notes: str
    tone: str = "neutral"


class InvestPeaseViewResponse(BaseModel):
    stance: str
    stance_label: str
    summary: str
    coverage_pct: Decimal
    looks_good: list[str] = Field(default_factory=list)
    watch_outs: list[str] = Field(default_factory=list)
    factors: list[InvestPeaseFactorResponse] = Field(default_factory=list)
    radar_note: str | None = None
    source: str | None = None
    warnings: list[str] = Field(default_factory=list)


class InvestInstrumentResearchResponse(BaseModel):
    ticker: str
    name: str
    generated_at: datetime
    overview: str
    sections: list[InvestResearchSectionResponse] = Field(default_factory=list)
    pease_view: InvestPeaseViewResponse | None = None
    withheld_capital_signals: list[str] = Field(default_factory=list)
    news_href: str | None = None


class InvestRiskCheckResponse(BaseModel):
    code: str
    level: str
    message: str
    passed: bool


class InvestFixedIncomeCashflowResponse(BaseModel):
    payment_date: str
    cashflow_type: str
    amount_per_100: Decimal
    description: str


class InvestFixedIncomeProductResponse(BaseModel):
    ticker: str
    name: str
    market: str
    currency: str
    issuer: str
    instrument_type: str
    tenor: str
    maturity_date: str | None = None
    indicative_yield_pct: Decimal | None = None
    coupon_rate_pct: Decimal | None = None
    settlement_date: str | None = None
    days_to_maturity: int | None = None
    clean_price: Decimal | None = None
    accrued_interest: Decimal | None = None
    dirty_price: Decimal | None = None
    yield_to_maturity_pct: Decimal | None = None
    next_coupon_date: str | None = None
    face_value_increment: Decimal | None = None
    quote_status: str | None = None
    quote_source: str | None = None
    quote_as_of: datetime | None = None
    quote_stale: bool = False
    minimum_order_amount: Decimal
    liquidity: str
    risk_level: str
    expected_payout: str
    trade_status: str
    proxy_ticker: str | None = None
    proxy_label: str | None = None
    retail_notes: list[str] = Field(default_factory=list)
    pricing_assumptions: list[str] = Field(default_factory=list)
    cashflows: list[InvestFixedIncomeCashflowResponse] = Field(default_factory=list)
    risk_checks: list[InvestRiskCheckResponse] = Field(default_factory=list)


class InvestMarketSessionResponse(BaseModel):
    market: str
    label: str
    is_open: bool


class InvestMarketQuoteResponse(BaseModel):
    ticker: str
    label: str
    name: str
    market: str
    group: str
    trade_status: str
    currency: str
    price: Decimal | None = None
    change_pct: Decimal | None = None
    as_of: datetime | None = None
    quote_status: str
    href: str


class InvestMarketBoardResponse(BaseModel):
    id: str
    title: str
    description: str
    items: list[InvestMarketQuoteResponse] = Field(default_factory=list)


class InvestMarketsResponse(BaseModel):
    generated_at: datetime
    summary: str
    sessions: list[InvestMarketSessionResponse] = Field(default_factory=list)
    boards: list[InvestMarketBoardResponse] = Field(default_factory=list)
    fixed_income: list[InvestFixedIncomeProductResponse] = Field(default_factory=list)


class InvestDiscoverItemResponse(BaseModel):
    title: str
    subtitle: str | None = None
    badge: str | None = None
    href: str | None = None
    tone: str = "neutral"
    metadata: list[str] = Field(default_factory=list)


class InvestDiscoverSectionResponse(BaseModel):
    id: str
    title: str
    description: str
    items: list[InvestDiscoverItemResponse] = Field(default_factory=list)


class InvestDiscoverResponse(BaseModel):
    generated_at: datetime
    summary: str
    narrative: str | None = None
    sections: list[InvestDiscoverSectionResponse]
    next_actions: list[InvestDiscoverItemResponse] = Field(default_factory=list)


class InvestNewsItemResponse(BaseModel):
    id: UUID
    provider: str
    provider_id: str
    source_name: str | None = None
    title: str
    summary: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    crawled_at: datetime | None = None
    jurisdiction: str | None = None
    event_type: str | None = None
    sentiment_label: str | None = None
    sentiment_score: Decimal | None = None
    tickers: list[str] = Field(default_factory=list)
    starred: bool = False


class InvestNewsPaginationResponse(BaseModel):
    page: int
    page_size: int
    total: int
    has_next: bool
    has_previous: bool


class InvestNewsOverviewResponse(BaseModel):
    generated_at: datetime
    summary: str
    portfolio_tickers: list[str] = Field(default_factory=list)
    watchlist_tickers: list[str] = Field(default_factory=list)
    markets_tickers: list[str] = Field(default_factory=list)
    for_you: list[InvestNewsItemResponse] = Field(default_factory=list)
    portfolio_items: list[InvestNewsItemResponse] = Field(default_factory=list)
    watchlist_items: list[InvestNewsItemResponse] = Field(default_factory=list)
    markets_items: list[InvestNewsItemResponse] = Field(default_factory=list)
    income_tickers: list[str] = Field(default_factory=list)
    income_items: list[InvestNewsItemResponse] = Field(default_factory=list)
    headlines: list[InvestNewsItemResponse] = Field(default_factory=list)
    headlines_page: InvestNewsPaginationResponse
    ticker: str | None = None
    ticker_items: list[InvestNewsItemResponse] = Field(default_factory=list)
    ticker_page: InvestNewsPaginationResponse | None = None
    saved_items: list[InvestNewsItemResponse] = Field(default_factory=list)


class InvestTransactionResponse(BaseModel):
    id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    ticker: str | None = None
    occurred_at: datetime
    description: str | None = None


class InvestProfilePermissionResponse(BaseModel):
    code: str
    label: str
    enabled: bool
    description: str


class InvestProfileActivityResponse(BaseModel):
    event: str
    message: str
    occurred_at: datetime
    level: str


class InvestProfileResponse(BaseModel):
    user_id: str
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    account: InvestAccountResponse
    permissions: list[InvestProfilePermissionResponse] = Field(default_factory=list)
    product_boundary: list[str] = Field(default_factory=list)
    notification_settings: list[str] = Field(default_factory=list)
    recent_activity: list[InvestProfileActivityResponse] = Field(default_factory=list)
