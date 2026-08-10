from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class MonthlyReportMetric(BaseModel):
    label: str
    value: str


class MonthlyReportPosition(BaseModel):
    ticker: str
    name: str
    asset_class: str
    market_value: Decimal
    portfolio_weight_pct: Decimal
    unrealized_pnl: Decimal


class MonthlyReportMemo(BaseModel):
    ticker: str
    memo_date: str
    classification: str
    action: str | None = None
    composite_score: Decimal | None = None


class MonthlyReportResponse(BaseModel):
    month: str
    generated_at: datetime
    portfolio_name: str
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    monthly_cash_flow: Decimal
    monthly_trade_count: int
    monthly_memo_count: int
    risk_warning_count: int
    metrics: list[MonthlyReportMetric]
    top_positions: list[MonthlyReportPosition]
    recent_memos: list[MonthlyReportMemo]
    risk_warnings: list[str] = Field(default_factory=list)
    model_registry_summary: list[MonthlyReportMetric] = Field(default_factory=list)
    commentary: str
