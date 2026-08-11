from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ResearchLabSummaryResponse(BaseModel):
    portfolio_name: str
    nav: Decimal
    research_memo_count: int
    active_opportunity_count: int
    dataset_count: int
    feature_set_count: int
    model_count: int
    backtest_count: int
    warning_count: int


class ResearchPipelineStageResponse(BaseModel):
    key: str
    label: str
    count: int
    description: str


class ResearchDatasetResponse(BaseModel):
    key: str
    name: str
    source: str
    row_count: int
    instrument_count: int
    latest_observation: date | datetime | None = None
    frequency: str
    status: str
    validation_summary: str


class ResearchFeatureSetResponse(BaseModel):
    feature_version: str
    snapshot_count: int
    instrument_count: int
    feature_count: int
    first_as_of_date: date | None = None
    last_as_of_date: date | None = None
    average_quality_score: Decimal | None = None
    status: str
    notes: str


class ResearchNotebookResponse(BaseModel):
    id: UUID
    title: str
    ticker: str
    classification: str
    memo_date: date
    status: str
    linked_recommendation_id: UUID | None = None
    summary: str


class ResearchExperimentResponse(BaseModel):
    id: UUID
    name: str
    experiment_type: str
    status: str
    hypothesis: str
    feature_version: str | None = None
    horizon_days: int | None = None
    validation_metric: str | None = None
    validation_value: Decimal | None = None
    created_at: datetime


class ResearchBacktestResponse(BaseModel):
    id: str
    name: str
    status: str
    strategy: str
    benchmark: str | None = None
    cost_model: str
    latest_run_at: datetime | None = None
    primary_metric: str | None = None
    notes: str


class ResearchModelResponse(BaseModel):
    model_version_id: UUID
    model_name: str
    model_version: str
    purpose: str
    feature_version: str | None = None
    horizon_days: int | None = None
    training_rows: int | None = None
    validation_rows: int | None = None
    validation_directional_accuracy: Decimal | None = None
    validation_r2: Decimal | None = None
    status: str
    created_at: datetime


class ResearchValidationCheckResponse(BaseModel):
    key: str
    label: str
    status: str
    detail: str


class ResearchActionItemResponse(BaseModel):
    key: str
    label: str
    priority: str
    owner_area: str
    detail: str
    action_path: str | None = None


class ResearchLabOverviewResponse(BaseModel):
    generated_at: datetime
    summary: ResearchLabSummaryResponse
    pipeline: list[ResearchPipelineStageResponse]
    datasets: list[ResearchDatasetResponse]
    feature_sets: list[ResearchFeatureSetResponse]
    notebooks: list[ResearchNotebookResponse]
    experiments: list[ResearchExperimentResponse]
    backtests: list[ResearchBacktestResponse]
    models: list[ResearchModelResponse]
    validation_checks: list[ResearchValidationCheckResponse]
    action_items: list[ResearchActionItemResponse]
    notes: list[str] = Field(default_factory=list)
