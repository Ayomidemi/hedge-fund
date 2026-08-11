from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SystemLogEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    level: str
    category: str
    event: str
    message: str
    context: dict[str, Any]
    created_at: datetime


class AdministrationModelVersionResponse(BaseModel):
    id: UUID
    name: str
    version: str
    pod: str
    purpose: str
    approved_use: str | None
    shutdown_criteria: str | None
    validation_status: str
    created_at: datetime


class AdministrationDataVersionResponse(BaseModel):
    key: str
    label: str
    record_count: int
    instrument_count: int
    latest_as_of_date: date | None


class AdministrationPortfolioRuleResponse(BaseModel):
    name: str
    limit_type: str
    threshold_value: Decimal
    unit: str
    scope: str


class AdministrationRiskPolicyResponse(BaseModel):
    id: UUID
    name: str
    version: str
    status: str
    effective_at: datetime
    limit_count: int
    notes: str | None


class PriceRefreshRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    started_at: datetime
    finished_at: datetime | None
    status: str
    ticker_count: int
    success_count: int
    failure_count: int
    positions_marked: int
    interval_seconds: int
    errors: list[dict[str, Any]]


class FxRateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    base_currency: str
    quote_currency: str
    rate: Decimal
    source: str
    as_of: datetime
    is_stale: bool


class AdministrationOverviewResponse(BaseModel):
    generated_at: datetime
    portfolio_name: str
    system_logs: list[SystemLogEntryResponse]
    model_versions: list[AdministrationModelVersionResponse]
    data_versions: list[AdministrationDataVersionResponse]
    portfolio_rules: list[AdministrationPortfolioRuleResponse]
    risk_policies: list[AdministrationRiskPolicyResponse]
    price_refresh_runs: list[PriceRefreshRunResponse] = []
    latest_fx_rate: FxRateResponse | None = None
