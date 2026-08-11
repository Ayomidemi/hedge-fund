from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.api.schemas.operating_core import InstrumentResponse


class AttributionSummaryResponse(BaseModel):
    portfolio_id: UUID
    portfolio_name: str
    generated_at: datetime
    period_start: date | None = None
    period_end: date
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    net_external_flow: Decimal
    total_deposits: Decimal
    total_withdrawals: Decimal
    gross_traded_value: Decimal
    total_fees: Decimal
    gross_realized_pnl: Decimal
    unrealized_pnl: Decimal
    net_pnl: Decimal
    portfolio_pnl_from_nav: Decimal
    reconciliation_gap: Decimal
    total_return_pct: Decimal
    fee_drag_pct: Decimal
    turnover_pct: Decimal
    hit_rate_pct: Decimal | None = None
    profit_factor: Decimal | None = None
    trade_count: int
    closed_trade_count: int
    winning_trade_count: int
    losing_trade_count: int


class AttributionRowResponse(BaseModel):
    instrument: InstrumentResponse
    status: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    portfolio_weight_pct: Decimal
    gross_buys: Decimal
    gross_sells: Decimal
    gross_realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    contribution_pct_nav: Decimal
    return_on_traded_capital_pct: Decimal
    trade_count: int
    closed_trade_count: int
    win_rate_pct: Decimal | None = None


class AttributionBucketResponse(BaseModel):
    name: str
    exposure_pct: Decimal
    market_value: Decimal
    gross_traded_value: Decimal
    gross_realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    net_pnl: Decimal
    contribution_pct_nav: Decimal
    instrument_count: int


class AttributionRealizedEventResponse(BaseModel):
    trade_id: UUID
    trade_date: datetime
    instrument: InstrumentResponse
    quantity: Decimal
    exit_price: Decimal
    average_cost: Decimal
    gross_realized_pnl: Decimal
    fees: Decimal
    net_realized_pnl: Decimal
    return_pct: Decimal


class AttributionReportResponse(BaseModel):
    summary: AttributionSummaryResponse
    by_ticker: list[AttributionRowResponse]
    by_asset_class: list[AttributionBucketResponse]
    by_sector: list[AttributionBucketResponse]
    realized_events: list[AttributionRealizedEventResponse]
    notes: list[str] = Field(default_factory=list)
