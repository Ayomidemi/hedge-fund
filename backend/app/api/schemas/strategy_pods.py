from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StrategyPodStatus = Literal[
    "active", "watch", "research", "sandbox", "suspended", "retired"
]
StrategyPodLifecycle = Literal[
    "research",
    "candidate",
    "paper_trading",
    "probationary_capital",
    "core_strategy",
    "reduced_allocation",
    "suspended",
    "retired",
]
StrategyPodCategory = Literal["alpha", "hedge", "treasury"]
StrategyPodLiveScope = Literal["yes", "limited", "paper", "research"]


class StrategyPodSignalResponse(BaseModel):
    key: str
    label: str
    value: str
    status: str
    detail: str | None = None
    as_of_date: date | None = None


class StrategyPodLatestSnapshotResponse(BaseModel):
    snapshot_id: UUID
    captured_at: datetime
    as_of_date: date
    current_signal_score: Decimal | None = None
    model_confidence: Decimal | None = None
    risk_level: str
    allocation_recommendation: str


class StrategyPodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    pod_category: str
    live_scope: str
    mandate: str
    status: str
    lifecycle_stage: str
    capital_allocation_pct: Decimal
    risk_budget_pct: Decimal
    volatility_target_pct: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    turnover_ceiling_pct: Decimal | None = None
    approved_instruments: list[str]
    shutdown_criteria: str | None = None
    notes: str | None = None
    current_signals: dict[str, Any]
    evaluation: dict[str, Any]
    live_signals: list[StrategyPodSignalResponse]
    current_signal_score: Decimal | None = None
    model_confidence: Decimal | None = None
    risk_level: str
    allocation_recommendation: str
    open_risk_warnings: list[str] = Field(default_factory=list)
    latest_snapshot: StrategyPodLatestSnapshotResponse | None = None


class StrategyPodOverviewResponse(BaseModel):
    generated_at: datetime
    portfolio_name: str
    nav: Decimal
    risk_level: str
    cash_pct: Decimal | None = None
    allocation_total_pct: Decimal
    alpha_allocation_total_pct: Decimal
    treasury_target_pct: Decimal
    risk_budget_total_pct: Decimal
    unallocated_pct: Decimal
    alpha_pods: list[StrategyPodResponse]
    hedge_pods: list[StrategyPodResponse]
    treasury_pods: list[StrategyPodResponse]
    pods: list[StrategyPodResponse]
    warnings: list[str] = Field(default_factory=list)


class StrategyPodUpdate(BaseModel):
    status: StrategyPodStatus | None = None
    lifecycle_stage: StrategyPodLifecycle | None = None
    capital_allocation_pct: Decimal | None = Field(default=None, ge=0, le=100)
    risk_budget_pct: Decimal | None = Field(default=None, ge=0, le=100)
    volatility_target_pct: Decimal | None = Field(default=None, ge=0, le=100)
    max_drawdown_pct: Decimal | None = Field(default=None, ge=0, le=100)
    turnover_ceiling_pct: Decimal | None = Field(default=None, ge=0)
    approved_instruments: list[str] | None = None
    shutdown_criteria: str | None = None
    notes: str | None = None


class StrategyPodSnapshotResponse(BaseModel):
    snapshot_id: UUID
    strategy_pod_id: UUID
    code: str
    captured_at: datetime
    as_of_date: date
    status: str
    lifecycle_stage: str
    capital_allocation_pct: Decimal
    risk_budget_pct: Decimal
    current_signal_score: Decimal | None = None
    model_confidence: Decimal | None = None
    risk_level: str
    allocation_recommendation: str
