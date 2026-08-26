from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.api.schemas.attribution import AttributionReportResponse


ReportKind = Literal["daily", "weekly", "monthly", "quarterly", "annual"]


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


class MonthlyReportAttributionRow(BaseModel):
    ticker: str
    name: str
    net_pnl: Decimal
    contribution_pct_nav: Decimal
    portfolio_weight_pct: Decimal


class MonthlyReportAttributionSummary(BaseModel):
    net_pnl: Decimal
    total_return_pct: Decimal
    total_fees: Decimal
    turnover_pct: Decimal
    hit_rate_pct: Decimal | None = None
    top_contributors: list[MonthlyReportAttributionRow] = Field(default_factory=list)
    top_detractors: list[MonthlyReportAttributionRow] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportBenchmarkSummary(BaseModel):
    benchmark_symbol: str
    benchmark_name: str
    period_return_pct: Decimal | None = None
    cumulative_return_pct: Decimal | None = None
    relative_return_pct: Decimal | None = None
    status: str
    notes: list[str] = Field(default_factory=list)


class ReportCompactSection(BaseModel):
    title: str
    items: list[MonthlyReportMetric] = Field(default_factory=list)
    note: str | None = None


class MonthlyReportResponse(BaseModel):
    report_kind: ReportKind = "monthly"
    report_title: str
    period_key: str
    period_label: str
    month: str
    portfolio_id: UUID
    period_start: date
    period_end: date
    reporting_mode: str
    generated_at: datetime
    portfolio_name: str
    nav: Decimal
    cash_balance: Decimal
    invested_value: Decimal
    period_cash_flow: Decimal
    period_trade_count: int
    period_memo_count: int
    monthly_cash_flow: Decimal
    monthly_trade_count: int
    monthly_memo_count: int
    risk_warning_count: int
    cumulative_return_pct: Decimal | None = None
    metrics: list[MonthlyReportMetric]
    top_positions: list[MonthlyReportPosition]
    recent_memos: list[MonthlyReportMemo]
    risk_warnings: list[str] = Field(default_factory=list)
    model_registry_summary: list[MonthlyReportMetric] = Field(default_factory=list)
    research_summary: list[MonthlyReportMetric] = Field(default_factory=list)
    attribution: MonthlyReportAttributionSummary | None = None
    attribution_detail: AttributionReportResponse | None = None
    benchmark_summary: ReportBenchmarkSummary | None = None
    ai_overview: ReportCompactSection
    portfolio_positioning: ReportCompactSection
    market_commentary: ReportCompactSection
    strategy_changes: ReportCompactSection
    research_pipeline: ReportCompactSection
    commentary: str


class ReportSnapshotCreate(BaseModel):
    report_kind: ReportKind = Field(
        default="monthly",
        validation_alias=AliasChoices("report_kind", "kind"),
    )
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    quarter: int | None = Field(default=None, ge=1, le=4)
    as_of: date | None = None


class ReportSnapshotUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class ReportSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_kind: ReportKind
    period_label: str
    period_start: date
    period_end: date
    title: str
    nav: Decimal | None = None
    return_pct: Decimal | None = None
    created_at: datetime
    updated_at: datetime
    payload_version: int = 1
    payload: dict | None = None
