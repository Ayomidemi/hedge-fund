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
    quantity: Decimal
    average_cost: Decimal
    current_price: Decimal | None = None
    market_value: Decimal
    unrealized_pnl: Decimal
    unrealized_pnl_pct: Decimal | None = None


class InvestHomeResponse(BaseModel):
    account: InvestAccountResponse
    portfolio_value: Decimal
    cash: Decimal
    invested: Decimal
    today_change: Decimal | None = None
    today_change_pct: Decimal | None = None
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
    side: str
    order_type: str
    quantity: Decimal | None
    notional: Decimal | None
    status: str
    submitted_at: datetime
    filled_at: datetime | None = None
    average_fill_price: Decimal | None = None
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
    notes: str | None = None
    date_added: datetime
    price: Decimal | None = None
    change_pct: Decimal | None = None


class InvestInstrumentResponse(BaseModel):
    ticker: str
    name: str
    asset_class: str
    exchange: str | None = None
    currency: str
    sector: str | None = None
    industry: str | None = None
    price: Decimal | None = None


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
    minimum_order_amount: Decimal
    liquidity: str
    risk_level: str
    expected_payout: str
    trade_status: str
    proxy_ticker: str | None = None
    proxy_label: str | None = None
    retail_notes: list[str] = Field(default_factory=list)
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
    sections: list[InvestDiscoverSectionResponse]
    next_actions: list[InvestDiscoverItemResponse] = Field(default_factory=list)


class InvestTransactionResponse(BaseModel):
    id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    ticker: str | None = None
    occurred_at: datetime
    description: str | None = None
