from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InstrumentCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=255)
    asset_class: str = Field(pattern="^(equity|etf|bond|commodity|cash_equivalent|other)$")
    exchange: str | None = Field(default=None, max_length=64)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    sector: str | None = Field(default=None, max_length=128)
    industry: str | None = Field(default=None, max_length=128)

    @field_validator("ticker", "currency")
    @classmethod
    def uppercase_code(cls, value: str) -> str:
        return value.strip().upper()


class CashLedgerEntryCreate(BaseModel):
    entry_date: date = Field(default_factory=date.today)
    amount: Decimal
    currency: str = Field(default="USD", min_length=3, max_length=3)
    entry_type: str = Field(default="deposit", min_length=1, max_length=64)
    description: str | None = None
    source_reference: str | None = None

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.strip().upper()


class ManualTradeCreate(BaseModel):
    instrument: InstrumentCreate
    side: str = Field(pattern="^(buy|sell)$")
    quantity: Decimal = Field(gt=0)
    price: Decimal = Field(gt=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    trade_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    rationale: str = Field(min_length=1)
    risk_notes: str | None = None
    broker_reference: str | None = None


class PortfolioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    base_currency: str
    mandate: str | None
    initial_capital: Decimal


class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticker: str
    name: str
    asset_class: str
    exchange: str | None
    currency: str
    sector: str | None
    industry: str | None


class CashLedgerEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    portfolio_id: UUID
    entry_date: date
    amount: Decimal
    currency: str
    entry_type: str
    description: str | None
    source_reference: str | None


class PositionResponse(BaseModel):
    id: UUID
    instrument: InstrumentResponse
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class TradeResponse(BaseModel):
    id: UUID
    instrument: InstrumentResponse
    trade_date: datetime
    side: str
    status: str
    quantity: Decimal
    executed_price: Decimal | None
    fees: Decimal
    rationale: str
    risk_notes: str | None
    broker_reference: str | None


class RiskLimitResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    limit_type: str
    threshold_value: Decimal
    unit: str
    scope: str
    severity: str
    is_active: bool
    notes: str | None


class RiskCheckResponse(BaseModel):
    name: str
    limit_type: str
    observed_value: Decimal
    threshold_value: Decimal
    unit: str
    passed: bool
    severity: str
    message: str


class ExposureBucketResponse(BaseModel):
    name: str
    exposure_pct: Decimal


class PortfolioDashboardResponse(BaseModel):
    portfolio: PortfolioResponse
    cash_balance: Decimal
    nav: Decimal
    invested_value: Decimal
    open_position_count: int
    trade_count: int
    positions: list[PositionResponse]
    recent_cash_entries: list[CashLedgerEntryResponse]
    recent_trades: list[TradeResponse]
    risk_limits: list[RiskLimitResponse]
    risk_checks: list[RiskCheckResponse]
    asset_class_exposure: list[ExposureBucketResponse]
    sector_exposure: list[ExposureBucketResponse]
