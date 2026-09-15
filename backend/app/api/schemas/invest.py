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


class InvestTransactionResponse(BaseModel):
    id: UUID
    entry_type: str
    amount: Decimal
    currency: str
    ticker: str | None = None
    occurred_at: datetime
    description: str | None = None
