from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from app.api.schemas.operating_core import PortfolioDashboardResponse


class PaperStart(BaseModel):
    # Compatibility for older clients only; never funds or resets the account.
    starting_cash: Decimal = Field(default=Decimal("10000"), ge=10000, le=10000, allow_inf_nan=False)
    duration_days: int = Field(default=7, ge=7, le=7)


class RiskProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    profile: Literal["low", "medium", "high"]
    expected_profile: Literal["low", "medium", "high"]


class PaperRunResponse(BaseModel):
    id: UUID
    status: Literal["running", "paused", "liquidating", "completed", "halted"]
    starting_cash: Decimal
    cash_balance: Decimal
    reserved_cash: Decimal
    available_cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    return_pct: Decimal
    max_drawdown_pct: Decimal
    fees_paid: Decimal
    started_at: datetime
    ends_at: datetime
    last_cycle_at: datetime | None
    completed_at: datetime | None
    halt_reason: str | None


class PaperOrderResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    status: Literal["pending", "open", "closed", "cancelled", "expired"]
    quantity: int
    limit_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    entry_price: Decimal | None
    exit_price: Decimal | None
    mark_price: Decimal | None
    realized_pnl: Decimal
    fees_paid: Decimal
    created_at: datetime
    expires_at: datetime
    opened_at: datetime | None
    closed_at: datetime | None
    exit_reason: str | None
    thesis: str


class PaperEquityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    recorded_at: datetime
    equity: Decimal
    cash_balance: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    drawdown_pct: Decimal


class PaperFundResponse(BaseModel):
    generated_at: datetime
    trading_mode: Literal["manual", "automatic"] = "manual"
    capital: PortfolioDashboardResponse | None = None
    run: PaperRunResponse | None
    orders: list[PaperOrderResponse]
    equity_history: list[PaperEquityResponse]
    blockers: list[str]
    policy: dict
    simulation_notice: str
